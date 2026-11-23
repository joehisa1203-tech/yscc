FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Tokyo

WORKDIR /app

# tzdata: scheduler and article dates are decided in JST, not container UTC.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY automation/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# The site itself is bind-mounted at runtime so generated articles and photos
# land in the repository, not inside the image.
CMD ["python", "-m", "automation.app.run_once"]
