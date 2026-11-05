"""Text typed on a step (the keywords of a search) feeds its input; a link into it wins."""

from uuid import UUID, uuid4

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.core.email import FakeEmailSender
from recruitai.modules.agents.blocks import tools
from recruitai.modules.agents.flows import engine
from tests.e2e_radar_fakes import Provider
from tests.integration.test_flows import (
    BASE,
    edge,
    input_node,
    make_flow,
    org_of,
    output_node,
    tool_node,
)


class Recording(Provider):
    def __init__(self) -> None:
        self.queries: list[object] = []

    async def search(self, **kw: object):  # type: ignore[override]
        self.queries.append(kw.get("query"))
        return await super().search(**kw)


async def test_text_typed_on_a_step_is_its_input_and_a_link_wins_over_it(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada
):
    org = await org_of(client, ada)
    provider = Recording()
    kit = tools.ToolKit(
        fetch=lambda url: None,  # type: ignore[arg-type,return-value]
        jobs=provider,
        mail=FakeEmailSender(),  # type: ignore[arg-type]
    )
    i, search, o = input_node("q"), tool_node("job_search"), output_node("n")
    search["fixed"] = {"query": "AI engineer Paris"}

    async def run(flow: dict, inputs: dict[str, str]) -> dict:
        r = await client.post(
            f"{BASE}/flows/{flow['id']}/runs", headers=ada, json={"inputs": inputs}
        )
        await engine.execute(
            db_session, fake_llm, org_id=org, run_id=UUID(r.json()["id"]), kit=kit
        )
        return (
            await client.get(f"{BASE}/flow-runs/{r.json()['id']}", headers=ada)
        ).json()

    # nothing is linked into "query": the typed words are used, and the step is "connected"
    flow = await make_flow(
        client, ada, [i, search, o],
        [edge(i, search, {}), edge(search, o, {"n": "{{count}}"})],
    )  # fmt: skip
    detail = (await client.get(f"{BASE}/flows/{flow['id']}", headers=ada)).json()
    assert not [x for x in detail["issues"] if x["code"] == "unmapped_input"]
    assert (await run(flow, {"q": "ignored"}))["status"] == "done"
    assert provider.queries == ["AI engineer Paris"]

    # a link into the same input owns it: the typed text is ignored
    j, search2, o2 = input_node("q"), tool_node("job_search"), output_node("n")
    search2["fixed"] = {"query": "AI engineer Paris"}
    flow2 = await make_flow(
        client, ada, [j, search2, o2],
        [edge(j, search2, {"query": "{{q}}"}), edge(search2, o2, {"n": "{{count}}"})],
    )  # fmt: skip
    await run(flow2, {"q": "data analyst Lyon"})
    assert provider.queries[-1] == "data analyst Lyon"

    # a link whose source was skipped (a branch not taken) still owns its input: typed text never
    # fills it in, so the step is skipped as it always was, not run on stale words
    c, search3, o3 = input_node("q"), tool_node("job_search"), output_node("n")
    cond = {"type": "condition", "id": str(uuid4()), "op": "eq", "value": "go"}
    mid = {"type": "transform", "id": str(uuid4()), "op": "trim"}
    search3["fixed"] = {"query": "stale words"}
    flow3 = await make_flow(
        client, ada, [c, cond, mid, search3, o3],
        [
            edge(c, cond, {"value": "{{q}}"}),
            edge(cond, mid, {"text": "{{value}}"}, port="true"),
            edge(mid, search3, {"query": "{{text}}"}),
            edge(c, search3, {"department": "{{q}}"}),  # a live link: the step has something to run on
            edge(search3, o3, {"n": "{{count}}"}),
        ],
    )  # fmt: skip
    before = len(provider.queries)
    await run(flow3, {"q": "stop"})
    assert (
        len(provider.queries) == before
    )  # the true-branch step was skipped, not run on "stale words"

    # an address to open can never be typed on a step (the page reader only follows a link)
    page = tool_node("read_page")
    page["fixed"] = {"url": "https://example.com"}
    k, k_out = input_node("q"), output_node("t")
    bad = await client.post(
        f"{BASE}/flows",
        headers=ada,
        json={
            "name": "bad",
            "graph": {"schema_version": 1, "nodes": [k, page, k_out], "edges": []},
        },
    )
    assert bad.status_code == 422
