import os
from dataclasses import dataclass
from typing import List
from unittest import mock

import pytest
import voluptuous as vol
from kubernetes.client import CoreV1Api
from kubernetes.client import V1SecretList

from takeoff.application_version import ApplicationVersion
from takeoff.azure.deploy_to_kubernetes import DeployToKubernetes, BaseKubernetes
from takeoff.credentials.secret import Secret
from tests.azure import takeoff_config

env_variables = {
    "AZURE_TENANTID": "David",
    "AZURE_KEYVAULT_SP_USERNAME_DEV": "Doctor",
    "AZURE_KEYVAULT_SP_PASSWORD_DEV": "Who",
    "CI_PROJECT_NAME": "my_little_pony",
    "CI_COMMIT_REF_SLUG": "my-little-pony",
}


@dataclass
class KubernetesResponse:
    namespace: str

    def to_dict(self):
        return {"items": [{"metadata": {"name": "something"}}]}


@dataclass
class RegistryCredentials:
    registry: str
    username: str
    password: str

    def credentials(self, config):
        return self


BASE_CONF = {"task": "deploy_to_kubernetes"}


@pytest.fixture(scope="session")
def victim():
    with mock.patch.dict(os.environ, env_variables), \
         mock.patch("takeoff.step.ApplicationName.get", return_value="my_little_pony"), \
         mock.patch("takeoff.azure.deploy_to_kubernetes.KeyVaultClient.vault_and_client", return_value=(None, None)):
        conf = {**takeoff_config(), **BASE_CONF}
        conf["azure"].update({"kubernetes_naming": "kubernetes{env}"})
        return DeployToKubernetes(ApplicationVersion("dev", "v", "branch"), conf)


class TestDeployToKubernetes(object):
    @mock.patch("takeoff.step.ApplicationName.get", return_value="my_little_pony")
    @mock.patch("takeoff.azure.deploy_to_kubernetes.KeyVaultClient.vault_and_client", return_value=(None, None))
    def test_validate_minimal_schema(self, _, __):
        conf = {**takeoff_config(), **BASE_CONF}
        conf["azure"].update({"kubernetes_naming": "kubernetes{env}"})

        res = DeployToKubernetes(ApplicationVersion("dev", "v", "branch"), conf)
        res.config["deployment_config_path"] = "kubernetes_config/deployment.yaml.j2"
        res.config["service_config_path"] = "kubernetes_config/service.yaml.j2"
        res.config["service"] = []

    @mock.patch("takeoff.step.ApplicationName.get", return_value="my_little_pony")
    @mock.patch("takeoff.azure.deploy_to_kubernetes.KeyVaultClient.vault_and_client", return_value=(None, None))
    def test_validate_schema_invalid_ip(self, _, __):
        conf = {**takeoff_config(), **BASE_CONF, "service_ips": {"dev": "Dave"}}
        conf["azure"].update({"kubernetes_naming": "kubernetes{env}"})

        with pytest.raises(vol.MultipleInvalid):
            DeployToKubernetes(ApplicationVersion("dev", "v", "branch"), conf)

    def test_is_needle_in_haystack(self):
        haystack = KubernetesResponse("hello").to_dict()
        assert DeployToKubernetes.is_needle_in_haystack("something", haystack)

    def test_find_unfindable_needle(self):
        haystack = KubernetesResponse("hello").to_dict()
        assert not DeployToKubernetes.is_needle_in_haystack(
            "my-unfindable-needle", haystack
        )

    def test_kubernetes_resource_exists(self, victim):
        assert victim._kubernetes_resource_exists("something", "", KubernetesResponse)

    def test_kubernetes_resource_does_not_exist(self, victim):
        assert not victim._kubernetes_resource_exists(
            "unfindable", "", KubernetesResponse
        )

    @mock.patch("kubernetes.client.CoreV1Api.list_namespace", return_value=KubernetesResponse("hello"))
    def test_kubernetes_namespace_exists(self, _, victim):
        assert victim._kubernetes_namespace_exists("something")

    @mock.patch("kubernetes.client.CoreV1Api.list_namespace", return_value=KubernetesResponse("hello"))
    def test_kubernetes_namespace_does_not_exist(self, _, victim):
        assert not victim._kubernetes_namespace_exists("unfindable")

    @mock.patch.object(DeployToKubernetes, "is_needle_in_haystack", return_value=False)
    def test_create_resource(self, _, victim):
        with mock.patch.object(
                CoreV1Api, "list_namespaced_secret", return_value=(V1SecretList(items=[]))
        ) as mock_list:
            with mock.patch.object(
                    CoreV1Api, "patch_namespaced_secret", return_value=None
            ) as mock_patch:
                with mock.patch.object(
                        CoreV1Api, "create_namespaced_secret", return_value=None
                ) as mock_create:
                    victim._create_or_patch_resource(
                        client=CoreV1Api,
                        resource_type="secret",
                        name="some_secret",
                        namespace="some_namespace",
                        resource_config={},
                    )
        mock_list.assert_called_once_with(namespace="some_namespace")
        mock_create.assert_called_once_with(namespace="some_namespace", body={})
        mock_patch.assert_not_called()

    @mock.patch.object(DeployToKubernetes, "is_needle_in_haystack", return_value=True)
    def test_patch_resource(self, _, victim):
        with mock.patch.object(
                CoreV1Api, "list_namespaced_secret", return_value=(V1SecretList(items=[]))
        ) as mock_list:
            with mock.patch.object(
                    CoreV1Api, "patch_namespaced_secret", return_value=None
            ) as mock_patch:
                with mock.patch.object(
                        CoreV1Api, "create_namespaced_secret", return_value=None
                ) as mock_create:
                    victim._create_or_patch_resource(
                        client=CoreV1Api,
                        resource_type="secret",
                        name="some_secret",
                        namespace="some_namespace",
                        resource_config={},
                    )
                    mock_list.assert_called_once_with(namespace="some_namespace")
                    mock_patch.assert_called_once_with(
                        name="some_secret", namespace="some_namespace", body={}
                    )
                    mock_create.assert_not_called()

    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_namespace_exists", return_value=False)
    def test_create_namespace_if_not_exists(self, _, victim):
        with mock.patch("kubernetes.client.CoreV1Api.create_namespace") as api_mock:
            victim._create_namespace_if_not_exists("blabla")
        api_mock.assert_called_once()

    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_namespace_exists", return_value=True)
    def test_create_namespace_if_exists(self, _, victim):
        with mock.patch.object(victim.core_v1_api, "create_namespace") as api_mock:
            victim._create_namespace_if_not_exists("blabla")
        api_mock.assert_not_called()

    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_resource_exists", return_value=True)
    def test_patch_resource_service(self, _, victim):
        with mock.patch.object(
                victim.core_v1_api, "patch_namespaced_service"
        ) as api_mock:
            victim._create_or_patch_resource(
                victim.core_v1_api, "service", "some_service", "some_namespace", {}
            )
        api_mock.assert_called_once_with(
            name="some_service", namespace="some_namespace", body={}
        )

    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_resource_exists", return_value=False)
    def test_create_resource_service(self, _, victim):
        with mock.patch.object(
                victim.core_v1_api, "create_namespaced_service"
        ) as api_mock:
            victim._create_or_patch_resource(
                victim.core_v1_api, "service", "some_service", "some_namespace", {}
            )
        api_mock.assert_called_once_with(namespace="some_namespace", body={})

    @mock.patch.dict(os.environ, env_variables)
    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_resource_exists", return_value=False)
    def test_create_deployment(self, _, victim):
        with mock.patch.object(
                victim.extensions_v1_beta_api, "create_namespaced_deployment"
        ) as create_mock:
            with mock.patch.object(
                    victim.extensions_v1_beta_api, "patch_namespaced_deployment"
            ) as patch_mock:
                victim._create_or_patch_deployment({}, "some_namespace")
        create_mock.assert_called_once_with(namespace="some_namespace", body={})
        patch_mock.assert_not_called()

    @mock.patch.dict(os.environ, env_variables)
    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_resource_exists", return_value=True)
    def test_patch_deployment(self, _, victim):
        with mock.patch.object(
                victim.extensions_v1_beta_api, "create_namespaced_deployment"
        ) as create_mock:
            with mock.patch.object(
                    victim.extensions_v1_beta_api, "patch_namespaced_deployment"
            ) as patch_mock:
                victim._create_or_patch_deployment({}, "some_namespace")
        patch_mock.assert_called_once_with(
            name="my_little_pony", namespace="some_namespace", body={}
        )
        create_mock.assert_not_called()

    @mock.patch.dict(os.environ, env_variables)
    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_resource_exists", return_value=False)
    def test_create_service(self, _, victim):
        metadata_config = {"metadata": {"name": "my-service"}}
        with mock.patch.object(
                victim.core_v1_api, "create_namespaced_service"
        ) as create_mock:
            with mock.patch.object(
                    victim.core_v1_api, "patch_namespaced_service"
            ) as patch_mock:
                victim._create_or_patch_service(metadata_config, "some_namespace")
        create_mock.assert_called_once_with(
            namespace="some_namespace", body=metadata_config
        )
        patch_mock.assert_not_called()

    @mock.patch.dict(os.environ, env_variables)
    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_resource_exists", return_value=True)
    def test_patch_service(self, _, victim):
        metadata_config = {"metadata": {"name": "my-service"}}
        with mock.patch.object(
                victim.core_v1_api, "create_namespaced_service"
        ) as create_mock:
            with mock.patch.object(
                    victim.core_v1_api, "patch_namespaced_service"
            ) as patch_mock:
                victim._create_or_patch_service(metadata_config, "some_namespace")
        patch_mock.assert_called_once_with(
            name="my-service",
            namespace="some_namespace",
            body={"metadata": {"name": "my-service"}},
        )
        create_mock.assert_not_called()

    @mock.patch.dict(os.environ, env_variables)
    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_resource_exists", return_value=False)
    def test_create_secrets(self, _, victim):
        secrets = [Secret(key="jack", val="the-ripper")]
        expected_body = {
            "api_version": None,
            "data": {"jack": "dGhlLXJpcHBlcg=="},
            "kind": None,
            "metadata": {
                "annotations": None,
                "cluster_name": None,
                "creation_timestamp": None,
                "deletion_grace_period_seconds": None,
                "deletion_timestamp": None,
                "finalizers": None,
                "generate_name": None,
                "generation": None,
                "initializers": None,
                "labels": None,
                "managed_fields": None,
                "name": "my_little_pony-secret",
                "namespace": None,
                "owner_references": None,
                "resource_version": None,
                "self_link": None,
                "uid": None,
            },
            "string_data": None,
            "type": "Opaque",
        }

        with mock.patch.object(
                victim.core_v1_api, "create_namespaced_secret"
        ) as create_mock:
            with mock.patch.object(
                    victim.core_v1_api, "patch_namespaced_secret"
            ) as patch_mock:
                victim._create_or_patch_secrets(secrets, "some_namespace")
        create_mock.assert_called_once_with(
            namespace="some_namespace", body=expected_body
        )
        patch_mock.assert_not_called()

    @mock.patch.dict(os.environ, env_variables)
    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_resource_exists", return_value=True)
    def test_patch_secret(self, _, victim):
        secrets = [Secret(key="jack", val="the-ripper")]
        expected_body = {
            "api_version": None,
            "data": {"jack": "dGhlLXJpcHBlcg=="},
            "kind": None,
            "metadata": {
                "annotations": None,
                "cluster_name": None,
                "creation_timestamp": None,
                "deletion_grace_period_seconds": None,
                "deletion_timestamp": None,
                "finalizers": None,
                "generate_name": None,
                "generation": None,
                "initializers": None,
                "labels": None,
                "managed_fields": None,
                "name": "my_little_pony-secret",
                "namespace": None,
                "owner_references": None,
                "resource_version": None,
                "self_link": None,
                "uid": None,
            },
            "string_data": None,
            "type": "Opaque",
        }

        with mock.patch.object(
                victim.core_v1_api, "create_namespaced_secret"
        ) as create_mock:
            with mock.patch.object(
                    victim.core_v1_api, "patch_namespaced_secret"
            ) as patch_mock:
                victim._create_or_patch_secrets(secrets, "some_namespace")
        patch_mock.assert_called_once_with(
            namespace="some_namespace", body=expected_body, name="my_little_pony-secret"
        )
        create_mock.assert_not_called()

    @mock.patch.dict(os.environ, env_variables)
    @mock.patch("takeoff.azure.deploy_to_kubernetes.DeployToKubernetes._kubernetes_resource_exists", return_value=False)
    def test_create_docker_registry_secret(self, _, victim):
        expected_body = {
            "api_version": None,
            "data": {
                ".dockerconfigjson": "eyJhdXRocyI6IHsibXktcmVnaXN0cnkiOiB7InVzZXJuYW1lIjogIm15LXVzZXJuYW1lIiwgInBhc3N3b3JkIjogIm15LXBhc3N3b3JkIiwgImF1dGgiOiAiYlhrdGRYTmxjbTVoYldVNmJYa3RjR0Z6YzNkdmNtUT0ifX19"
            },
            "kind": None,
            "metadata": {
                "annotations": None,
                "cluster_name": None,
                "creation_timestamp": None,
                "deletion_grace_period_seconds": None,
                "deletion_timestamp": None,
                "finalizers": None,
                "generate_name": None,
                "generation": None,
                "initializers": None,
                "labels": None,
                "managed_fields": None,
                "name": "acr-auth",
                "namespace": None,
                "owner_references": None,
                "resource_version": None,
                "self_link": None,
                "uid": None,
            },
            "string_data": None,
            "type": "kubernetes.io/dockerconfigjson",
        }

        with mock.patch("takeoff.azure.deploy_to_kubernetes.DockerRegistry.credentials",
                        return_value=RegistryCredentials("my-registry", "my-username", "my-password")):
            with mock.patch.object(victim.core_v1_api, "create_namespaced_secret") as create_mock:
                with mock.patch.object(victim.core_v1_api, "patch_namespaced_secret") as patch_mock:
                    victim._create_docker_registry_secret()
        create_mock.assert_called_once_with(
            body=expected_body, namespace="my_little_pony"
        )
        patch_mock.assert_not_called()


@dataclass(frozen=True)
class MockValue:
    value: bytes


@dataclass(frozen=True)
class MockCredentialResults:
    kubeconfigs: List[MockValue]


class TestBaseKubernetes:
    @mock.patch.dict(os.environ, {"HOME": "myhome"})
    def test_write_kube_config(self, victim: BaseKubernetes):
        mopen = mock.mock_open()
        with mock.patch("os.mkdir") as m_mkdir:
            with mock.patch("builtins.open", mopen):
                victim._write_kube_config(
                    MockCredentialResults([MockValue("foo".encode(encoding="UTF-8"))])
                )

        m_mkdir.assert_called_once_with("myhome/.kube")
        mopen.assert_called_once_with("myhome/.kube/config", "w")
        mopen().write.assert_called_once_with("foo")
