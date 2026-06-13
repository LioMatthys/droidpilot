from droidpilot.ui import (
    by_resource_id,
    by_text,
    parse_hierarchy,
    summarize,
)

SAMPLE = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        package="life.overture.beam" content-desc="" bounds="[0,0][1080,2400]">
    <node index="0" text="Beam" resource-id="" class="android.widget.TextView"
          package="life.overture.beam" clickable="false" bounds="[40,120][200,180]"/>
    <node index="1" text="Start sharing" resource-id="life.overture.beam:id/start"
          class="android.widget.Button" package="life.overture.beam"
          clickable="true" bounds="[100,1000][980,1120]"/>
    <node index="2" text="482915" resource-id="life.overture.beam:id/code"
          class="android.widget.TextView" package="life.overture.beam"
          clickable="false" bounds="[400,1300][680,1400]"/>
  </node>
</hierarchy>
"""


def test_parse_and_bounds():
    root = parse_hierarchy(SAMPLE)
    nodes = list(root.walk())
    # root + framelayout + 3 children
    assert len(nodes) == 5
    btn = root.find(by_text("Start sharing"))
    assert btn is not None
    assert btn.clickable is True
    assert btn.bounds == (100, 1000, 980, 1120)
    assert btn.center == (540, 1060)


def test_text_selectors():
    root = parse_hierarchy(SAMPLE)
    assert root.find(by_text("sharing")) is not None  # substring
    assert root.find(by_text("SHARING")) is not None  # case-insensitive
    assert root.find(by_text("nope")) is None
    assert root.find(by_text("Start", exact=True)) is None  # exact requires full match


def test_resource_id_selector():
    root = parse_hierarchy(SAMPLE)
    code = root.find(by_resource_id("code"))
    assert code is not None and code.text == "482915"
    # full id also works
    assert root.find(by_resource_id("life.overture.beam:id/start")) is not None


def test_summarize_lists_clickables():
    out = summarize(parse_hierarchy(SAMPLE))
    assert "Start sharing" in out
    assert "[tap]" in out
    assert "482915" in out
