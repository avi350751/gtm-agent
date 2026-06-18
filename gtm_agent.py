"""
GTM Content Studio
==================
A small multi-agent system that turns a product, feature, or upcoming event
into a full go-to-market content suite, grounded in YOUR own documents.

Pipeline (LangGraph state machine):

    ingest docs -> retrieve -> strategist -> generate -> review
                                                ^            |
                                                |  needs     |
                                                +-- revision +  -> END (passed)

Agents:
  - strategist : reads RAG context, picks audience + tone + key messages
  - generator  : writes LinkedIn post, email, blog draft, and 3 ad variations
  - reviewer   : critiques for grounding, cross-format consistency, tone, and
                 sends the suite back for revision until it passes (or hits a cap)

I have selected OpenAI models for this exercise.
"""

import os
import sys
import glob
import json
from typing import TypedDict, List

from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFLoader, CSVLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import StateGraph, START, END

load_dotenv()


# --------------------------------------------------------------------------- #
# Model 
# --------------------------------------------------------------------------- #
def get_llm(temperature: float = 0.7):

    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=temperature,
    )


def get_embeddings():
    
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model="text-embedding-3-small")


# --------------------------------------------------------------------------- #
# Structured outputs (Pydantic) — each agent returns clean, typed data
# --------------------------------------------------------------------------- #
class Strategy(BaseModel):
    product_summary: str = Field(description="2-3 sentence summary, grounded in context")
    target_audience: str = Field(description="The single primary audience and why")
    tone: str = Field(description="Chosen tone, e.g. 'confident and technical'")
    value_props: List[str] = Field(description="3-5 grounded value propositions")
    key_messages: List[str] = Field(description="3-5 core messages to reinforce")
    call_to_action: str = Field(description="One clear CTA used across all formats")


class AdVariant(BaseModel):
    angle: str = Field(description="Creative angle, e.g. 'pain-point', 'benefit', 'curiosity'")
    headline: str = Field(description="<= 8 words")
    body: str = Field(description="1-2 short lines")


class Content(BaseModel):
    linkedin_post: str = Field(description="150-200 words, hook-first, ends with the CTA")
    email_subject: str
    email_body: str = Field(description="120-160 words, scannable, one CTA")
    blog_title: str
    blog_draft: str = Field(description="300-400 word short draft")
    ad_variations: List[AdVariant] = Field(description="Exactly 3 distinct variations")


class PieceCritique(BaseModel):
    piece: str = Field(description="Which piece, e.g. 'linkedin_post'")
    issues: List[str]
    suggestions: List[str]


class Review(BaseModel):
    grounded: bool = Field(description="True if every claim is supported by the context")
    consistent: bool = Field(description="True if naming/dates/CTA match across formats")
    tone_aligned: bool = Field(description="True if every piece matches the target tone")
    quality_score: int = Field(description="Overall quality, 1-10")
    needs_revision: bool = Field(description="True if score < 8 or any check failed")
    overall_feedback: str
    critiques: List[PieceCritique] = Field(description="Only for pieces that need work")


# --------------------------------------------------------------------------- #
# Graph state
# --------------------------------------------------------------------------- #
class GTMState(TypedDict, total=False):
    topic: str
    context: str
    strategy: dict
    content: dict
    review: dict
    revisions: int
    max_revisions: int


# --------------------------------------------------------------------------- #
# RAG ingestion
# --------------------------------------------------------------------------- #
def build_retriever(data_dir: str = "data", k: int = 5):
    docs = []
    for path in glob.glob(os.path.join(data_dir, "**", "*"), recursive=True):
        low = path.lower()
        if low.endswith(".pdf"):
            docs.extend(PyPDFLoader(path).load())
        elif low.endswith(".csv"):
            docs.extend(CSVLoader(path).load())
    if not docs:
        raise SystemExit(f"No PDF or CSV files found in ./{data_dir}. Add some and retry.")
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=120
    ).split_documents(docs)
    store = FAISS.from_documents(chunks, get_embeddings())
    return store.as_retriever(search_kwargs={"k": k})


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
STRATEGIST_PROMPT = """You are a senior go-to-market strategist.

TOPIC (product, feature, or event to promote):
{topic}

RETRIEVED SOURCE CONTEXT (your only factual ground truth):
{context}

Produce a tight GTM strategy. Rules:
- Ground every fact (specs, dates, prices, names) in the context above.
- If a detail is missing from context, stay general instead of inventing it.
- Choose ONE clear primary audience and a tone that fits them."""

GENERATE_PROMPT = """You are a multi-format GTM content creator.

TOPIC: {topic}

STRATEGY (follow the audience, tone, key messages, and CTA exactly):
{strategy}

SOURCE CONTEXT (ground all facts here; never invent specs, dates, or prices):
{context}
{feedback}
Write ready-to-edit content. Keep naming, dates, claims, and the CTA consistent
across ALL formats, in the strategy's target tone:
- LinkedIn post: 150-200 words, hook-first, at most 1-2 tasteful emojis, ends on the CTA.
- Email: a short subject line + 120-160 word body, scannable, one clear CTA.
- Blog: a title + a 300-400 word short draft with a clear intro and takeaway.
- Ads: exactly 3 variations, each a DIFFERENT angle (e.g. pain-point, benefit,
  curiosity), each with a headline (<= 8 words) and a 1-2 line body."""

REVISION_BLOCK = """
REVISION REQUESTED — address this reviewer feedback in your rewrite:
Overall: {feedback}
Per-piece critiques:
{critiques}
"""

REVIEW_PROMPT = """You are a meticulous content editor reviewing a GTM content suite.

SOURCE CONTEXT (ground truth):
{context}

STRATEGY (intended audience, tone, messages, CTA):
{strategy}

CONTENT TO REVIEW (JSON):
{content}

Evaluate on three axes:
1. Grounding   - flag any claim (spec, date, price, name, metric) not in the context.
2. Consistency - naming, dates, positioning, and CTA must match across all formats.
3. Tone        - every piece must match the strategy's target tone and audience.

Score 1-10 overall. Set needs_revision = true if the score is below 8 OR there is any
grounding or consistency failure. Give specific, actionable per-piece critiques only for
pieces that need work. Be concise and concrete."""


# --------------------------------------------------------------------------- #
# Build the LangGraph app (nodes close over the retriever)
# --------------------------------------------------------------------------- #
def build_app(retriever):

    def retrieve(state: GTMState):
        docs = retriever.invoke(state["topic"])
        context = "\n\n---\n\n".join(d.page_content for d in docs)
        return {"context": context}

    def strategist(state: GTMState):
        llm = get_llm(0.4).with_structured_output(Strategy)
        out = llm.invoke(STRATEGIST_PROMPT.format(
            topic=state["topic"], context=state["context"]))
        return {"strategy": out.model_dump()}

    def generate(state: GTMState):
        review = state.get("review")
        revisions = state.get("revisions", 0)
        feedback = ""
        if review:  # this is a revision pass
            revisions += 1
            feedback = REVISION_BLOCK.format(
                feedback=review["overall_feedback"],
                critiques=json.dumps(review["critiques"], indent=2),
            )
        llm = get_llm(0.8).with_structured_output(Content)
        out = llm.invoke(GENERATE_PROMPT.format(
            topic=state["topic"],
            strategy=json.dumps(state["strategy"], indent=2),
            context=state["context"][:4000],
            feedback=feedback,
        ))
        return {"content": out.model_dump(), "revisions": revisions}

    def review(state: GTMState):
        llm = get_llm(0.3).with_structured_output(Review)
        out = llm.invoke(REVIEW_PROMPT.format(
            context=state["context"][:3000],
            strategy=json.dumps(state["strategy"], indent=2),
            content=json.dumps(state["content"], indent=2),
        ))
        return {"review": out.model_dump()}

    def route(state: GTMState):
        r = state["review"]
        if r["needs_revision"] and state.get("revisions", 0) < state.get("max_revisions", 2):
            return "generate"
        return END

    g = StateGraph(GTMState)
    g.add_node("retrieve", retrieve)
    g.add_node("strategist", strategist)
    g.add_node("generate", generate)
    g.add_node("review", review)

    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "strategist")
    g.add_edge("strategist", "generate")
    g.add_edge("generate", "review")
    g.add_conditional_edges("review", route, {"generate": "generate", END: END})
    return g.compile()


# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #
def render(state: GTMState):
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule

    c = Console()
    s, co, r = state["strategy"], state["content"], state["review"]

    c.print(Rule("[bold]GTM STRATEGY[/bold]"))
    c.print(f"[bold]Audience:[/bold] {s['target_audience']}")
    c.print(f"[bold]Tone:[/bold] {s['tone']}")
    c.print(f"[bold]Value props:[/bold] " + "; ".join(s["value_props"]))
    c.print(f"[bold]CTA:[/bold] {s['call_to_action']}\n")

    c.print(Panel(co["linkedin_post"], title="LinkedIn Post", border_style="cyan"))
    c.print(Panel(f"[bold]Subject:[/bold] {co['email_subject']}\n\n{co['email_body']}",
                  title="Promotional Email", border_style="green"))
    c.print(Panel(f"[bold]{co['blog_title']}[/bold]\n\n{co['blog_draft']}",
                  title="Blog Draft", border_style="magenta"))
    ads = "\n\n".join(
        f"[bold]{a['angle']}[/bold] — {a['headline']}\n{a['body']}" for a in co["ad_variations"])
    c.print(Panel(ads, title="Ad Variations", border_style="yellow"))

    verdict = "PASSED" if not r["needs_revision"] else "NEEDS WORK (cap reached)"
    c.print(Rule("[bold]REVIEW[/bold]"))
    c.print(f"Score: {r['quality_score']}/10 | Grounded: {r['grounded']} | "
            f"Consistent: {r['consistent']} | Tone: {r['tone_aligned']} | Verdict: {verdict}")
    c.print(f"Revisions performed: {state.get('revisions', 0)}")
    c.print(f"\n{r['overall_feedback']}")


def save_markdown(state: GTMState, path: str = "gtm_output.md"):
    co, s = state["content"], state["strategy"]
    ads = "\n".join(f"**{a['angle']} — {a['headline']}**  \n{a['body']}\n"
                    for a in co["ad_variations"])
    md = f"""# GTM Content — {state['topic']}

**Audience:** {s['target_audience']}  
**Tone:** {s['tone']}  
**CTA:** {s['call_to_action']}

## LinkedIn Post
{co['linkedin_post']}

## Promotional Email
**Subject:** {co['email_subject']}

{co['email_body']}

## Blog Draft — {co['blog_title']}
{co['blog_draft']}

## Ad Variations
{ads}
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main():
    topic = " ".join(sys.argv[1:]).strip() or input("Product / feature / event > ").strip()
    if not topic:
        print("No topic provided.")
        return

    print("Building vector store from ./data ...")
    retriever = build_retriever()
    app = build_app(retriever)

    print(f"Generating GTM suite for: {topic}\n")
    result = app.invoke({"topic": topic, "revisions": 0, "max_revisions": 2})

    render(result)
    out_path = save_markdown(result)
    print(f"\nSaved editable draft -> {out_path}")


if __name__ == "__main__":
    main()
