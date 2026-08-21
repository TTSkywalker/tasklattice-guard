from dataclasses import replace
from typing import cast

import pytest

from runner.toolkit.policy_library import PolicyTag, PolicyTagNamespace, policies
from runner.toolkit.policy_library.registry import PolicyLibraryRegistry


def test_policy_library_uses_reviewed_facets_and_nemo_rail_terms() -> None:
    tags = [tag for policy in policies() for tag in policy.tags]
    namespaces = {tag.namespace for tag in tags}

    assert "scope" not in namespaces
    assert "stage" not in namespaces
    assert "rail" in namespaces
    assert ("rail:input", "Input rail") in {(tag.id, tag.label) for tag in tags}
    assert ("rail:output", "Output rail") in {(tag.id, tag.label) for tag in tags}


@pytest.mark.parametrize("namespace", ["scope", "stage"])
def test_policy_library_rejects_retired_facets(namespace: str) -> None:
    policy = policies()[0]
    retired_tag = PolicyTag(
        namespace=cast(PolicyTagNamespace, namespace),
        value="retired",
        label="Retired",
    )

    with pytest.raises(ValueError, match="unsupported tag namespace"):
        PolicyLibraryRegistry((replace(policy, tags=(retired_tag,)),))
