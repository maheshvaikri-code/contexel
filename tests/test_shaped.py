from contexel import shaped, stage, select, dedupe, pipeline


def test_shaped_with_stage_list():
    @shaped([stage(select, fields=["url"]), stage(dedupe, key="url")])
    def tool():
        return [{"url": "u1", "x": 1}, {"url": "u1", "x": 2}, {"url": "u2"}]

    assert tool() == [{"url": "u1"}, {"url": "u2"}]


def test_shaped_with_pipeline_callable():
    pipe = pipeline([stage(select, fields=["a"])])

    @shaped(pipe)
    def tool():
        return [{"a": 1, "b": 2}]

    assert tool() == [{"a": 1}]


def test_shaped_passes_args_through():
    @shaped([stage(select, fields=["q"])])
    def tool(query, limit=10):
        return [{"q": query, "limit": limit, "junk": "x"}]

    assert tool("hi", limit=3) == [{"q": "hi"}]


def test_shaped_preserves_name_and_doc():
    @shaped([stage(select, fields=["a"])])
    def my_tool():
        """does a thing"""
        return [{"a": 1}]

    assert my_tool.__name__ == "my_tool"
    assert my_tool.__doc__ == "does a thing"
