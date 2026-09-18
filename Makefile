# Used only by `sam build` (Metadata: BuildMethod: makefile in
# infra/template.yaml). Not part of the uv-based local dev workflow.
#
# --platform/--only-binary/--python-version/--implementation tell pip to
# fetch prebuilt manylinux wheels for Lambda's actual runtime (x86_64,
# Python 3.12, CPython) regardless of the host OS building this -- verified
# this downloads real Linux ELF binaries for psycopg[binary]'s compiled
# extension even when run on macOS, so no Docker/--use-container is needed.
build-ApiFunction:
	pip install \
		--platform manylinux2014_x86_64 \
		--only-binary=:all: \
		--python-version 3.12 \
		--implementation cp \
		-r infra/requirements.txt \
		-t "$(ARTIFACTS_DIR)"
	cp -r src "$(ARTIFACTS_DIR)/src"
