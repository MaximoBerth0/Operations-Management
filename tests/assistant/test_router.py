async def test_chat_requires_assistant_permission(
    client, client_user, auth_headers, make_location, admin_user
):
    location_id = await make_location(admin_user)

    response = await client.post(
        "/assistant/chat",
        headers=auth_headers(client_user, location_id),
        json={"messages": [{"role": "user", "content": "what should I restock?"}]},
    )

    assert response.status_code == 403


async def test_chat_rejects_user_without_role(client, plain_user, auth_headers):
    response = await client.post(
        "/assistant/chat",
        headers=auth_headers(plain_user),
        json={"messages": [{"role": "user", "content": "what should I restock?"}]},
    )

    assert response.status_code == 403


def test_employee_and_admin_can_use_assistant():
    from app.common.constants.system_roles import SYSTEM_ROLES

    assert "assistant:use" in SYSTEM_ROLES["employee"]
    assert "assistant:use" in SYSTEM_ROLES["admin"]
    assert "assistant:use" not in SYSTEM_ROLES["client"]
