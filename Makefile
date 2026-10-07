# Every container command lives here. ARGS are the arguments of the program. EXTRA is for docker, e.g. a mount for shaders kept elsewhere.

IMAGE := $(notdir $(CURDIR))
WORK := /work
SHADER_DIR := /shader
PROGRAM := render.py
USER_FLAGS := --user $(shell id -u):$(shell id -g) -e HOME=/tmp
MOUNT := -v $(CURDIR):$(WORK) -w $(WORK)
RUN := docker run --rm --gpus all --network host $(USER_FLAGS) $(MOUNT) $(EXTRA)

.PHONY: help build gpu run stream shell

help:
	$(RUN) $(IMAGE) python $(PROGRAM) --help

build:
	docker build -t $(IMAGE) .

# lists the GPUs the container can use, to tell a real one from a software fallback
gpu:
	$(RUN) $(IMAGE) vulkaninfo --summary

# serves a shader live, or renders it to a file, depending on ARGS; the network is the host's, so any port can be served
run:
	$(RUN) $(IMAGE) python $(PROGRAM) $(ARGS)

# serves the shader FRAG (a path without spaces) at the resolution RES on a free port, and prints the address of the page
stream:
	$(RUN) -v $(abspath $(dir $(FRAG))):$(SHADER_DIR):ro $(IMAGE) python $(PROGRAM) $(SHADER_DIR)/$(notdir $(FRAG)) --out-res $(RES) --out-port 0

shell:
	$(RUN) -it $(IMAGE) bash
