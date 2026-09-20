"""
Image Upload API - Flask routes for pushing images to the display.

Registered onto the Flask app by flask_load() in flight-tracker.py,
which keeps web/app.py untouched.  The ingest endpoint authenticates
with an API key generated from the settings UI (the key store lives in
utilities/image_inbox.py); the key-management endpoints reuse the web
UI's session + CSRF.

Routes:

    POST   /api/image      push image(s)        (X-API-Key header)
    GET    /api/image-key  current key + status (web session)
    POST   /api/image-key  generate a new key
    DELETE /api/image-key  revoke the current key

The key-management endpoints read the same session keys the main app
uses ("authenticated", "csrf_token") but answer in JSON because they
are called from the Vue settings UI via fetch(), not page navigation.
"""

import logging
import secrets

from flask import jsonify, request, session

logger = logging.getLogger(__name__)


def _session_authenticated() -> bool:
    return bool(session.get("authenticated"))


def _csrf_ok() -> bool:
    """Header-based CSRF check for fetch() requests (X-CSRF-Token)."""
    supplied = str(request.headers.get("X-CSRF-Token", ""))
    expected = str(session.get("csrf_token", ""))
    return bool(supplied) and secrets.compare_digest(supplied, expected)


def register_image_api(app):
    """Add the image API routes to *app*."""

    # -- image ingest -----------------------------------------------------

    @app.route("/api/image", methods=["POST"])
    def api_image_submit():
        from utilities.image_inbox import (
            INBOX,
            ImageSubmissionError,
            api_key_configured,
            verify_api_key,
        )

        if not api_key_configured():
            logger.warning("Image upload rejected - no API key generated yet")
            return (
                jsonify(
                    {
                        "status": "error",
                        "error": "Image upload disabled - no API key has been generated",
                    }
                ),
                403,
            )

        provided = request.headers.get("X-API-Key", "")
        if not provided or not verify_api_key(provided):
            logger.warning("Image upload rejected - invalid or missing API key")
            return (
                jsonify({"status": "error", "error": "Invalid or missing API key"}),
                401,
            )

        payload = request.get_json(force=True, silent=True)
        if not isinstance(payload, dict):
            return (
                jsonify(
                    {"status": "error", "error": "Request body must be a JSON object"}
                ),
                400,
            )

        try:
            submission = INBOX.submit(payload)
        except ImageSubmissionError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400

        logger.info(
            "Image accepted: %d frame(s), ttl %ds",
            len(submission),
            submission.ttl_seconds,
        )
        response = {
            "status": "ok",
            "frames": len(submission),
            "ttl": submission.ttl_seconds,
        }
        if len(submission) > 1:
            from utilities.image_inbox import quantise_frame_delay

            hold, effective_ms = quantise_frame_delay(submission.frame_delay_ms)
            response["frame_delay_ms"] = submission.frame_delay_ms
            response["frame_hold"] = hold
            response["effective_frame_delay_ms"] = effective_ms
        return (jsonify(response), 200)

    # -- key management (web session) --------------------------------------

    @app.route("/api/image-key", methods=["GET"])
    def api_image_key_status():
        if not _session_authenticated():
            return jsonify({"error": "Not authenticated"}), 401
        from utilities.image_inbox import api_key_configured, get_api_key

        return jsonify({"configured": api_key_configured(), "key": get_api_key()})

    @app.route("/api/image-key", methods=["POST"])
    def api_image_key_generate():
        if not _session_authenticated():
            return jsonify({"error": "Not authenticated"}), 401
        if not _csrf_ok():
            return jsonify({"error": "Invalid CSRF token"}), 403

        from utilities.image_inbox import generate_api_key

        key = generate_api_key()
        logger.info("Image upload API key generated (old key revoked)")
        return jsonify({"key": key})

    @app.route("/api/image-key", methods=["DELETE"])
    def api_image_key_revoke():
        if not _session_authenticated():
            return jsonify({"error": "Not authenticated"}), 401
        if not _csrf_ok():
            return jsonify({"error": "Invalid CSRF token"}), 403

        from utilities.image_inbox import revoke_api_key

        revoke_api_key()
        logger.info("Image upload API key revoked")
        return jsonify({"status": "ok"})