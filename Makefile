DEV_IMAGE := ghcr.io/tasklattice/tasklattice-guard:dev
DEV_NAMESPACE := tali
HELM_RELEASE := tasklattice-guard
HELM_CHART := charts/tasklattice-guard
HELM_TIMEOUT ?= 180s
PORT ?= 8091
LOCAL_ENV_FILE := $(if $(wildcard .env),--env-file .env,)

.PHONY: sync test web-dev web-build run image helm-lint helm-template helm-install helm-test helm-uninstall deploy-local

sync:
	uv sync --all-extras --frozen
	cd web && npm ci

test:
	uv run python -m pytest -q
	cd web && npm run typecheck && npm run build

web-dev:
	cd web && npm run dev

web-build:
	cd web && npm run build

run:
	uv run $(LOCAL_ENV_FILE) python -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

image:
	docker build --tag $(DEV_IMAGE) .

helm-lint:
	helm lint $(HELM_CHART) --strict

helm-template:
	helm template $(HELM_RELEASE) $(HELM_CHART) --namespace $(DEV_NAMESPACE)

helm-install: image helm-lint
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
		--namespace $(DEV_NAMESPACE) \
		--create-namespace \
		--set image.tag=dev \
		--wait \
		--timeout $(HELM_TIMEOUT)
	kubectl --namespace $(DEV_NAMESPACE) rollout restart deployment/$(HELM_RELEASE)
	kubectl --namespace $(DEV_NAMESPACE) rollout status deployment/$(HELM_RELEASE) --timeout=$(HELM_TIMEOUT)

helm-test:
	helm test $(HELM_RELEASE) --namespace $(DEV_NAMESPACE)

helm-uninstall:
	helm uninstall $(HELM_RELEASE) --namespace $(DEV_NAMESPACE)

deploy-local: helm-install
