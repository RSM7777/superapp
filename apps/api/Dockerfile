FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
# Deps-only layer for caching; the stub package satisfies setuptools until the
# real source is copied over it.
RUN mkdir -p superapp && touch superapp/__init__.py && pip install --no-cache-dir -e ".[llm]"
COPY . .
RUN pip install --no-cache-dir -e ".[llm]"
EXPOSE 8000
# Migrate, then serve. The old CMD started uvicorn straight into main.py's
# create_all, which races Alembic and cannot add columns to existing tables;
# a schema change then failed at the first request, not at boot.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "superapp.main:app", "--host", "0.0.0.0", "--port", "8000"]
