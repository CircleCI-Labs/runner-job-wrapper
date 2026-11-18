.PHONY: all lint test check

SCRIPT := bin/circleci-job-wrapper

all: check

lint:
	shellcheck $(SCRIPT) test/fixtures/fake-agent test/test_helper.bash
	bash -n $(SCRIPT)

test:
	bats test/

check: lint test
