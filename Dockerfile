FROM python:3.10.10-slim
WORKDIR /app
COPY frozen_panes.css image_zoom.js quality_reviews.py quality.html server.py edit_capture.py delete_capture.py ingestion.py index.html coverage.html ingestion.html search.html capture_review.js terminal.css /app/
EXPOSE 8080
CMD ["python", "-u", "/app/server.py"]
