CONTAINER_NAME := hephalump
IMAGE_NAME := hephalump
#
DEBUG_CONTAINER_NAME := hephalump-debug
DEBUG_IMAGE_NAME := hephalump-debug
#
DOCKERHUB_IMAGE := hephalump2/hephalump
TAG := latest
#
PLATFORM := linux/amd64
PORTS := -p 8080:8080 -p 2222:22

.PHONY: build run debug-build debug-run push

build:
	docker build --platform $(PLATFORM) -t $(IMAGE_NAME):$(TAG) .

run:
	docker run --rm --platform $(PLATFORM) \
		--mount type=bind,src="$(HOME)/Desktop/cs6250/github_repos/hephalump/autograder_test_submission",target=/autograder/submission \
		--mount type=bind,src="$(HOME)/Desktop/cs6250/github_repos/hephalump/autograder_source",target=/autograder/updated_files \
		--mount type=bind,src="/tmp",target=/autograder/results \
		$(IMAGE_NAME):$(TAG) \
		/autograder/run_autograder && cat /tmp/results.json

# 		-v ./autograder_test_submission:/autograder/submission \
# 		-v ./autograder_source:/autograder/updated_files \
# 		-v /tmp:/autograder/results \

push:
	docker tag $(IMAGE_NAME):$(TAG) $(DOCKERHUB_IMAGE):$(TAG)
	docker push $(DOCKERHUB_IMAGE):$(TAG)


debug-build:
	docker build -f Dockerfile.debug --platform $(PLATFORM) -t $(DEBUG_IMAGE_NAME) .

debug-run:
	docker run -d \
		--platform $(PLATFORM) \
		$(PORTS) \
		--mount type=bind,src="$(HOME)/Desktop/cs6250/github_repos/hephalump/autograder_test_submission",target=/autograder/submission \
		--mount type=bind,src="$(HOME)/Desktop/cs6250/github_repos/hephalump/autograder_source",target=/autograder/updated_files \
		$(DEBUG_IMAGE_NAME)

debug-rm:
	docker rm -f $(DEBUG_CONTAINER_NAME)

# docker run --rm --platform linux/amd64 -v ./autograder_test_submission:/autograder/submission -v ./autograder_source:/autograder/updated_files -v /tmp:/autograder/results hephalump:latest /autograder/run_autograder && cat /tmp/results.json
