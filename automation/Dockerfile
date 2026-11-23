FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Tokyo

WORKDIR /app

# tzdata: scheduler and article dates are decided in JST, not container UTC.
# openssh-client: git push to GitHub over SSH needs it; without it push fails.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata git ca-certificates openssh-client \
 && rm -rf /var/lib/apt/lists/*

# ssh は getpwuid() でユーザーを引くため、実行UIDが /etc/passwd に無いと
# "No user exists for uid" で push できない。ホストのUIDと同じユーザーを作る。
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g "${APP_GID}" app 2>/dev/null || true \
 && useradd -u "${APP_UID}" -g "${APP_GID}" -m -d /home/app -s /bin/bash app 2>/dev/null || true

COPY automation/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# The site itself is bind-mounted at runtime so generated articles and photos
# land in the repository, not inside the image.
CMD ["python", "-m", "automation.app.run_once"]
