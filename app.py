"""
Local Flask UI for GTM Content Studio.
The vector store is built once on the first request and reused afterwards.
"""
from flask import Flask, render_template, request, jsonify
import logging

import gtm_agent as G

# Configure Flask with correct static folder path
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="templates/static",
    static_url_path="/static"
)

# Setup logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache the compiled pipeline (and its FAISS store) across requests.
_pipeline = {"app": None, "error": None}


def get_pipeline():
    """Build and cache the pipeline on first request."""
    if _pipeline["app"] is None:
        try:
            logger.info("Building retriever from ./data ...")
            retriever = G.build_retriever()
            logger.info("Building LangGraph application...")
            _pipeline["app"] = G.build_app(retriever)
            logger.info("Pipeline ready.")
        except Exception as e:
            logger.error(f"Failed to build pipeline: {e}", exc_info=True)
            _pipeline["error"] = str(e)
            raise
    
    if _pipeline["error"]:
        raise RuntimeError(_pipeline["error"])
    
    return _pipeline["app"]


@app.route("/")
def index():
    """Serve the main UI."""
    try:
        return render_template("index.html")
    except Exception as e:
        logger.error(f"Error rendering template: {e}", exc_info=True)
        return f"Error loading UI: {e}", 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "pipeline_ready": _pipeline["app"] is not None}), 200


@app.route("/generate", methods=["POST"])
def generate():
    """Generate GTM content suite from a topic."""
    try:
        data = request.get_json(silent=True) or {}
        topic = (data.get("topic") or "").strip()
        
        if not topic:
            return jsonify({
                "error": "Please enter a product, feature, or event."
            }), 400

        # Get parameters
        try:
            max_revisions = int(data.get("max_revisions", 2))
        except (ValueError, TypeError):
            max_revisions = 2

        logger.info(f"Generating content for topic: {topic}")
        
        # Get or build the pipeline
        pipeline = get_pipeline()
        
        # Invoke the pipeline
        logger.info(f"Invoking pipeline with max_revisions={max_revisions}")
        result = pipeline.invoke({
            "topic": topic,
            "revisions": 0,
            "max_revisions": max_revisions
        })
        
        # Extract and validate response structure
        strategy = result.get("strategy") or {}
        content = result.get("content") or {}
        review = result.get("review") or {}
        revisions = result.get("revisions", 0)
        
        logger.info(f"Pipeline executed successfully. Revisions: {revisions}")
        
        # Build and return response
        response = {
            "topic": topic,
            "strategy": strategy,
            "content": content,
            "review": review,
            "revisions": revisions,
        }
        
        return jsonify(response), 200
    
    except Exception as exc:
        # Surface a readable error message in the UI
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        logger.error(f"Error during generation: {error_msg}", exc_info=True)
        return jsonify({"error": error_msg}), 500


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("GTM Content Studio Web Server")
    logger.info("=" * 60)
    logger.info("Starting Flask app on http://127.0.0.1:5000")
    logger.info("Press Ctrl+C to stop the server")
    logger.info("=" * 60)
    
    try:
        app.run(
            host="127.0.0.1",
            port=5000,
            debug=True,
            threaded=True,
            use_reloader=True
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user.")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
