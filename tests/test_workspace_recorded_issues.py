"""A persisted review is visible only on the project and revision that supplied it."""

from fastapi.testclient import TestClient

from scan_api.workspace_server import create_app
from test_workspace import account, create, fixture_graph, settled


def test_saved_review_is_bound_to_the_owned_artifact(tmp_path):
    def reviewed(url, directory, stop):
        result = fixture_graph(url, directory, stop)
        route = result["graph"]["routes"][0]
        result["review"] = {
            "repositoryUrl": url, "resolvedRevision": result["graph"]["repo"]["revision"],
            "model": "recorded", "agentCount": 1, "agreementThreshold": 1,
            "votes": [{"id": "v", "check": "existing", "routeId": route["id"], "role": "skeptic",
                       "verdict": "present", "reason": "Saved review feedback."}],
            "findings": [{"id": "f", "check": "existing", "routeId": route["id"],
                          "agreementThreshold": 1, "presentCount": 1, "voteIds": ["v"]}],
        }
        return result

    with TestClient(create_app(tmp_path, build=reviewed)) as client:
        account(client, "owner")
        project = create(client, "recorded")
        assert settled(client, project)["findings"][0]["id"] == "f"
    with TestClient(create_app(tmp_path, build=fixture_graph)) as client:
        account(client, "owner", login=True)
        path = "/projects/" + project["id"]
        scan = client.get(path).json()["project"]["scan"]
        assert scan["votes"][0]["routeId"] == client.get(path + "/graph").json()["routes"][0]["id"]
        account(client, "neighbor")
        assert client.get(path).status_code == 404
        other = create(client, "recorded")
        assert settled(client, other)["findings"] == []
