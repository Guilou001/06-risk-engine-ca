# Prérequis : uv (https://docs.astral.sh/uv/)
UV ?= uv

setup:
	$(UV) sync --locked --all-extras

test:             ## 10 tests synthétiques : quantiles, fuite, récupération GARCH, juges (sans réseau)
	$(UV) run pytest

lint:
	$(UV) run ruff check src tests

backtest:         ## 6 modèles x 5 476 jours x 2 niveaux (12 s mesurées ; exige `rke fetch` d'abord)
	$(UV) run rke backtest
