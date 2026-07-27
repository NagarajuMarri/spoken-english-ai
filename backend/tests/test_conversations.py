def test_scenario_listing(client):
    response = client.get("/api/v1/scenarios")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == [
        "Daily Conversation",
        "Workplace English",
        "Job Interview",
        "Travel",
        "Shopping",
        "Doctor Visit",
        "Telephone Conversation",
        "Free Talk",
    ]


def test_conversation_creation(client, learner):
    response = client.post(
        "/api/v1/conversations",
        json={"learner_id": learner["id"], "scenario_id": "travel"},
    )

    assert response.status_code == 201
    assert response.json()["scenario_id"] == "travel"
    assert response.json()["messages"] == []
    assert response.json()["opening_prompt"]


def test_conversation_creation_rejects_missing_learner(client):
    response = client.post(
        "/api/v1/conversations",
        json={"learner_id": "missing", "scenario_id": "travel"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "learner_not_found"


def test_conversation_creation_rejects_invalid_scenario(client, learner):
    response = client.post(
        "/api/v1/conversations",
        json={"learner_id": learner["id"], "scenario_id": "unknown"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "scenario_not_found"


def test_deterministic_message_and_correction(client, conversation):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "I am go to office yesterday."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["turn_number"] == 1
    assert body["tutor_response"] == "I see. What did you do at the office?"
    assert body["correction_summary"] == 'You can say: “I went to the office yesterday.”'
    assert body["transcript_entry"]["learner_text"] == "I am go to office yesterday."


def test_normal_message_continues_without_forced_correction(client, conversation):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "I enjoy reading books."},
    )

    assert response.status_code == 200
    assert response.json()["correction_summary"] is None
    assert response.json()["tutor_response"].startswith("Thanks")


def test_telugu_explanation_flag(client, conversation):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={
            "text": "I am go to office yesterday.",
            "include_telugu_explanation": True,
        },
    )

    assert response.status_code == 200
    assert "తెలుగు:" in response.json()["correction_summary"]


def test_empty_message_is_structured_error(client, conversation):
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"text": "   "},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_message"


def test_missing_conversation(client):
    response = client.get("/api/v1/conversations/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"


def test_transcript_retrieval_preserves_turns(client, conversation):
    for text in ["Hello there.", "I am go to office yesterday."]:
        response = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"text": text},
        )
        assert response.status_code == 200

    response = client.get(f"/api/v1/conversations/{conversation['id']}")

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [item["turn_number"] for item in messages] == [1, 2]
    assert [item["learner_text"] for item in messages] == [
        "Hello there.",
        "I am go to office yesterday.",
    ]
