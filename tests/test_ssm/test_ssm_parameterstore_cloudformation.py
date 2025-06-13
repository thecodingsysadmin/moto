import json
from unittest.mock import MagicMock, patch

import boto3
import botocore.exceptions
import pytest

from moto import mock_aws
from moto.ssm.models import Parameter


# Test to check if delete_parameter is called with the correct resource name
@pytest.mark.parametrize(
    "resource_name,expected_name",
    [
        ("fake-param", "fake-param"),  # Parameter exists and has Name property
        (
            None,
            "fake-param",
        ),  # No Parameter name provided, should use from resource_json
    ],
)
def test_delete_from_cloudformation_json(
    resource_name,
    expected_name,
):
    account_id = "123456789012"
    region = "us-east-1"
    resource_json = {
        "Properties": {
            "Name": "fake-param",
            "Type": "String",
            "Value": "test",
            "Overwrite": "true",
        }
    }
    with patch("moto.ssm.models.ssm_backends") as mock_backends:
        mock_backend = MagicMock()
        mock_backends.__getitem__.return_value = {region: mock_backend}
        Parameter.delete_from_cloudformation_json(
            resource_name,
            resource_json,
            account_id,
            region,
        )
        mock_backend.delete_parameter.assert_called_once_with(expected_name)


@mock_aws
def test_cloudformation_lifecycle():
    ssm_param_name = "test"
    ssm_param_value = "initial value"
    stack_template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Test Stack",
        "Resources": {
            "SSMParameter": {
                "Type": "AWS::SSM::Parameter",
                "Properties": {
                    "Name": ssm_param_name,
                    "Type": "String",
                    "Value": ssm_param_value,
                },
            }
        },
    }

    cloudformation_client = boto3.client("cloudformation", region_name="us-east-1")

    stack_template_str = json.dumps(stack_template)

    cloudformation_client.create_stack(
        StackName="test_stack",
        TemplateBody=stack_template_str,
        Capabilities=("CAPABILITY_IAM",),
    )

    client = boto3.client("ssm", region_name="us-east-1")
    resp = client.get_parameter(Name=ssm_param_name)["Parameter"]
    resp_param_name = resp["Name"]
    resp_param_value = resp["Value"]

    assert resp_param_name == ssm_param_name
    assert resp_param_value == ssm_param_value

    # Update the stack template with new value

    new_ssm_param_value = "updated value"

    stack_template["Resources"]["SSMParameter"]["Properties"]["Value"] = (
        new_ssm_param_value
    )
    stack_template_str = json.dumps(stack_template)
    cloudformation_client.update_stack(
        StackName="test_stack",
        TemplateBody=stack_template_str,
        Capabilities=("CAPABILITY_IAM",),
    )

    resp = client.get_parameter(Name=ssm_param_name)["Parameter"]
    resp_param_name = resp["Name"]
    resp_param_value = resp["Value"]

    assert resp_param_name == ssm_param_name
    assert resp_param_value == new_ssm_param_value

    # Stack deletion

    cloudformation_client.delete_stack(StackName="test_stack")
    with pytest.raises(botocore.exceptions.ClientError) as exc:
        resp = client.get_parameter(Name=ssm_param_name)["Parameter"]
    err = exc.value.response["Error"]
    assert err["Code"] == "ParameterNotFound"
    assert err["Message"] == f"Parameter {ssm_param_name} not found."


@mock_aws
def test_cloudformation_lifecycle_with_parsing():
    ssm_param_name = "test"
    ssm_param_value = "initial value"
    stack_template = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Test Stack",
        "Parameters": {
            "Name": {"Type": "String", "Default": ssm_param_name},
            "Value": {"Type": "String", "Default": ssm_param_value},
        },
        "Resources": {
            "SSMParameter": {
                "Type": "AWS::SSM::Parameter",
                "Properties": {
                    "Name": {"Fn::Sub": "${Name}"},
                    "Type": "String",
                    "Value": {"Ref": "Value"},
                },
            }
        },
    }

    cloudformation_client = boto3.client("cloudformation", region_name="us-east-1")

    stack_template_str = json.dumps(stack_template)

    cloudformation_client.create_stack(
        StackName="test_stack",
        TemplateBody=stack_template_str,
        Capabilities=("CAPABILITY_IAM",),
    )

    cloudformation_client.describe_stack_resources(StackName="test_stack")

    client = boto3.client("ssm", region_name="us-east-1")
    resp = client.get_parameter(Name=ssm_param_name)
    resp_param = resp.get("Parameter")
    resp_param_name = resp_param["Name"]
    resp_param_value = resp_param["Value"]

    assert resp_param_name == ssm_param_name
    assert resp_param_value == ssm_param_value

    # Update the stack with new value

    new_ssm_param_value = "updated value"

    stack_template_str = json.dumps(stack_template)
    cloudformation_client.update_stack(
        StackName="test_stack",
        TemplateBody=stack_template_str,
        Capabilities=("CAPABILITY_IAM",),
        Parameters=[{"ParameterKey": "Value", "ParameterValue": new_ssm_param_value}],
    )

    resp = client.get_parameter(Name=ssm_param_name)["Parameter"]
    resp_param_name = resp["Name"]
    resp_param_value = resp["Value"]

    assert resp_param_name == ssm_param_name
    assert resp_param_value == new_ssm_param_value

    # Stack deletion

    cloudformation_client.delete_stack(StackName="test_stack")
    with pytest.raises(botocore.exceptions.ClientError) as exc:
        resp = client.get_parameter(Name=ssm_param_name)["Parameter"]
    err = exc.value.response["Error"]
    assert err["Code"] == "ParameterNotFound"
    assert err["Message"] == f"Parameter {ssm_param_name} not found."
