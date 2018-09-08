import os
import unittest
from unittest import mock

from sdh_deployment.create_appservice_and_webapp import (
    CreateAppserviceAndWebapp as victim,
    CosmosCredentials,
)
from sdh_deployment.create_appservice_and_webapp import (
    SiteConfig,
    AppService,
    AppServiceSKU,
    WebApp,
    Site,
    RESOURCE_GROUP,
)
from sdh_deployment.run_deployment import ApplicationVersion
from sdh_deployment.util import SHARED_REGISTRY

ENV = ApplicationVersion("env", "ver")

VALID_SITE_CONFIG = SiteConfig(
    linux_fx_version=f"DOCKER|{SHARED_REGISTRY}/my-app:{ENV.version}",
    app_settings=[
        {"name": "DOCKER_ENABLE_CI", "value": True},
        {"name": "DOCKER_REGISTRY_SERVER_URL", "value": "https://" + SHARED_REGISTRY},
        {"name": "DOCKER_REGISTRY_SERVER_USERNAME", "value": "awesomeperson"},
        {"name": "DOCKER_REGISTRY_SERVER_PASSWORD", "value": "supersecret42"},
        {"name": "WEBSITE_HTTPLOGGING_RETENTION_DAYS", "value": 7},
        {"name": "COSMOS_URI", "value": "https://localhost:443"},
        {"name": "COSMOS_KEY", "value": "secretcosmoskey"},
        {"name": "INSTRUMENTATION_KEY", "value": "secret-insturmentation-key"},
    ],
)


class TestDeployToWebApp(unittest.TestCase):
    @mock.patch(
        "sdh_deployment.create_application_insights.CreateApplicationInsights.create_application_insights"
    )
    @mock.patch(
        "sdh_deployment.create_appservice_and_webapp.CreateAppserviceAndWebapp._get_cosmos_credentials"
    )
    @mock.patch.dict(
        os.environ,
        {
            "APPSERVICE_LOCATION": "west europe",
            "BUILD_DEFINITIONNAME": "my-build",
            "REGISTRY_USERNAME": "awesomeperson",
            "REGISTRY_PASSWORD": "supersecret42",
        },
    )
    def test_build_site_config(
        self, _get_cosmos_credentials_mock, create_application_insights_mock
    ):
        _get_cosmos_credentials_mock.return_value = CosmosCredentials(
            "https://localhost:443", "secretcosmoskey"
        )
        create_application_insights_mock.return_value.instrumentation_key = (
            "secret-insturmentation-key"
        )

        result = victim._build_site_config("my-app", ENV)
        assert result.app_settings == VALID_SITE_CONFIG.app_settings
        assert result == VALID_SITE_CONFIG

    @mock.patch.dict(os.environ, {"BUILD_DEFINITIONNAME": "my-build"})
    def test_parse_appservice_parameters_defaults(self):
        expected_appservice_config = AppService(
            name="my-build", sku=AppServiceSKU(name="S1", capacity=2, tier="Standard")
        )

        result = victim._parse_appservice_parameters(
            "prd", {"appService": {"name": "my-build"}}
        )

        assert expected_appservice_config == result

    @mock.patch.dict(os.environ, {"BUILD_DEFINITIONNAME": "my-build"})
    def test_parse_appservice_parameters_config_unavailable(self):
        expected_appservice_config = AppService(
            name="my-build", sku=AppServiceSKU(name="S1", capacity=2, tier="Standard")
        )

        result = victim._parse_appservice_parameters(
            "prd",
            {
                "appService": {
                    "name": "my-build",
                    "sku": {"acp": {"name": "I1", "capacity": 10, "tier": "uber"}},
                }
            },
        )

        assert expected_appservice_config == result

    @mock.patch(
        "sdh_deployment.create_appservice_and_webapp.CreateAppserviceAndWebapp._build_site_config"
    )
    @mock.patch(
        "sdh_deployment.create_appservice_and_webapp.CreateAppserviceAndWebapp._get_cosmos_credentials"
    )
    @mock.patch.dict(
        os.environ,
        {
            "APPSERVICE_LOCATION": "west europe",
            "BUILD_DEFINITIONNAME": "my-build",
            "REGISTRY_USERNAME": "user123",
            "REGISTRY_PASSWORD": "supersecret123",
        },
    )
    def test_get_webapp_to_create(
        self, _get_cosmos_credentials_mock, get_site_config_mock
    ):
        get_site_config_mock.return_value = VALID_SITE_CONFIG
        _get_cosmos_credentials_mock.return_value = CosmosCredentials(
            "https://localhost:443", "secretcosmoskey"
        )

        expected_result = WebApp(
            resource_group=RESOURCE_GROUP.format(dtap="dev"),
            name="my-build-dev",
            site=Site(
                location="west europe",
                site_config=VALID_SITE_CONFIG,
                server_farm_id="appservice_id",
            ),
        )

        result = victim._get_webapp_to_create("appservice_id", "dev", ENV)

        assert result == expected_result

        get_site_config_mock.assert_called_once()