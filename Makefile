node   := 01 # two-digit port number suffix (80xx)
nnodes := 21 # number of BPs

logging_json := logging.json
tmp_dirs     := nodes/ wallet/

export PATH := "$(HOME)/haya/build/bin/:$(PATH)"

default: help

.PHONY: help
help:
	@echo "Commands:"
	@echo
	@echo "  run      : run launcher.py ($(nnodes) nodes); params: nnodes=<n>"
	@echo "  get-info : get running node info; params: node=<n>"
	@echo "  kill     : kill all haya-node & haya-waller processes"
	@echo "  clean    : remove temp directories: $(tmp_dirs)"
	@echo
	@echo "Examples:"
	@echo
	@echo "  # run 5 block producers:"
	@echo "  make run nnodes=5"
	@echo
	@echo "  # use verbose logging settings file instead of the default one:"
	@echo "  make run logging_json=logging-verbose.json"
	@echo
	@echo "  # get info for node running on port 8002:"
	@echo "  make get-info node=02"

.PHONY: run
run:
	# TODO: set PATH globally in Makefile
	env PATH=$(PATH) python3 launcher.py --producer-limit=$(nnodes) \
	  --cleos haya-cli --nodeos haya-node --keosd haya-wallet \
	  -a --logging-json-path $(logging_json)

.PHONY: get-info
get-info:
	env PATH=$(PATH) haya-cli --url http://127.0.0.1:80$(node) get info

.PHONY: kill
kill:
	killall -9 haya-node haya-wallet || true

.PHONY: clean
clean:
	rm -rf $(tmp_dirs)
