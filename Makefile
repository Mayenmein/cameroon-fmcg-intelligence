ingest:
	python scripts/download_all.py

test:
	pytest

up:
	docker-compose up -d
