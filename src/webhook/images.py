import logging
import re
import threading

import docker
import mlflow
from docker.errors import ImageNotFound
from mlflow import MlflowClient
from mlflow.models import build_docker

from webhook.config import MLFLOW_TRACKING_URI


logger = logging.getLogger(__name__)
image_lock = threading.Lock()


def _image_repository(model_name: str) -> str:
    repository = re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-")
    if not repository:
        raise ValueError(f"Model name {model_name!r} cannot form a Docker image name")
    return repository


def _build_or_retag_champion(model_name: str, version: str) -> None:
    repository = _image_repository(model_name)
    version_image = f"{repository}:{version}"
    champion_image = f"{repository}:champion"
    client = docker.from_env()
    try:
        try:
            image = client.images.get(version_image)
            logger.info("Reusing local model image %s", version_image)
        except ImageNotFound:
            model_uri = f"models:/{model_name}/{version}"
            logger.info("Building Docker image %s from %s", version_image, model_uri)
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            build_docker(model_uri=model_uri, name=version_image)
            image = client.images.get(version_image)

        if not image.tag(repository, tag="champion"):
            raise RuntimeError(f"Failed to tag {version_image} as {champion_image}")
        logger.info("Tagged %s as %s", version_image, champion_image)
    finally:
        client.close()


def ensure_champion_image(model_name: str, version: str) -> None:
    with image_lock:
        _build_or_retag_champion(model_name, version)


def process_champion_alias_event(model_name: str, event_version: str) -> bool:
    with image_lock:
        registry_client = MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)
        current_version = registry_client.get_model_version_by_alias(
            model_name,
            "champion",
        ).version
        if str(current_version) != event_version:
            logger.info(
                "Skipping stale champion event for %s version %s; current champion is %s",
                model_name,
                event_version,
                current_version,
            )
            return False

        _build_or_retag_champion(model_name, event_version)
        return True
