# Pulizia.

.PHONY: clean
clean:
	rm -rf generated
	find . -path ./engine -prune -o -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache

.PHONY: clean-all
clean-all: clean
	rm -rf $(VENV) src/*.egg-info
