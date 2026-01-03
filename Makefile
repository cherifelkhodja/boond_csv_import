.PHONY: build up down logs shell clean dev

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

shell:
	docker-compose exec app bash

clean:
	docker-compose down -v --rmi all

dev:
	docker-compose up --build
