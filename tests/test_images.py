import unittest
from unittest.mock import Mock, patch

from docker.errors import ImageNotFound

from webhook.images import ensure_champion_image, process_champion_alias_event


class EnsureChampionImageTests(unittest.TestCase):
    @patch("webhook.images.mlflow.set_tracking_uri")
    @patch("webhook.images.build_docker")
    @patch("webhook.images.docker.from_env")
    def test_reuses_version_image_and_updates_champion_tag(
        self,
        from_env: Mock,
        build_docker: Mock,
        set_tracking_uri: Mock,
    ) -> None:
        image = Mock()
        image.tag.return_value = True
        docker_client = Mock()
        docker_client.images.get.return_value = image
        from_env.return_value = docker_client

        ensure_champion_image("property-rate", "5")

        build_docker.assert_not_called()
        image.tag.assert_called_once_with("property-rate", tag="champion")
        docker_client.close.assert_called_once()
        set_tracking_uri.assert_not_called()

    @patch("webhook.images.mlflow.set_tracking_uri")
    @patch("webhook.images.build_docker")
    @patch("webhook.images.docker.from_env")
    def test_builds_missing_version_image_then_tags_champion(
        self,
        from_env: Mock,
        build_docker: Mock,
        set_tracking_uri: Mock,
    ) -> None:
        image = Mock()
        image.tag.return_value = True
        docker_client = Mock()
        docker_client.images.get.side_effect = [ImageNotFound("missing"), image]
        from_env.return_value = docker_client

        ensure_champion_image("property-rate", "5")

        build_docker.assert_called_once_with(
            model_uri="models:/property-rate/5",
            name="property-rate:5",
        )
        image.tag.assert_called_once_with("property-rate", tag="champion")
        set_tracking_uri.assert_called_once()
        docker_client.close.assert_called_once()

    @patch("webhook.images._build_or_retag_champion")
    @patch("webhook.images.MlflowClient")
    def test_stale_alias_event_does_not_move_champion_tag(
        self,
        mlflow_client: Mock,
        build_or_retag: Mock,
    ) -> None:
        registry_client = Mock()
        registry_client.get_model_version_by_alias.return_value.version = "6"
        mlflow_client.return_value = registry_client

        processed = process_champion_alias_event("property-rate", "5")

        self.assertFalse(processed)
        build_or_retag.assert_not_called()

    @patch("webhook.images._build_or_retag_champion")
    @patch("webhook.images.MlflowClient")
    def test_current_alias_event_builds_or_retags_champion(
        self,
        mlflow_client: Mock,
        build_or_retag: Mock,
    ) -> None:
        registry_client = Mock()
        registry_client.get_model_version_by_alias.return_value.version = "5"
        mlflow_client.return_value = registry_client

        processed = process_champion_alias_event("property-rate", "5")

        self.assertTrue(processed)
        build_or_retag.assert_called_once_with("property-rate", "5")


if __name__ == "__main__":
    unittest.main()
