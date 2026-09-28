#!/usr/bin/env python3
"""Generate BT XML variants instrumented with RuntimeTrace marker actions.

The generated files are intended for runtime-overhead experiments. They do not
replace the baseline BTs; pass the generated filenames through `bt_xml_file` or
`bt_name` parameters when running the experiment.
"""

from __future__ import annotations

import argparse
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


def package_dir() -> Path:
    source_layout = Path(__file__).resolve().parents[1]
    if (source_layout / "bt_xml").exists():
        return source_layout
    from ament_index_python.packages import get_package_share_directory
    return Path(get_package_share_directory("cs4home_hri_challenge"))


PACKAGE = package_dir()
BT_DIR = PACKAGE / "bt_xml"

CAPABILITIES = {
    "greeting": ("greeting_guest.xml", "Greeting"),
    "describe_person": ("describe_person.xml", "Describe / Invite"),
    "introduce_guest": ("introduce_guest.xml", "Introduce Guest"),
    "find_seat": ("find_seat.xml", "Find Seat"),
    "grab_bag": ("grab_bag.xml", "Grab Bag"),
    "transport_bag": ("transport_bag.xml", "Transport Bag"),
    "recovery": ("recovery.xml", "Recovery"),
}

MODULAR = {filename: label for filename, label in CAPABILITIES.values()}


def trace(event: str, capability: str, architecture: str, details: str = "") -> ET.Element:
    attrs = {
        "ID": "RuntimeTrace",
        "event": event,
        "capability": capability,
        "architecture": architecture,
    }
    if details:
        attrs["details"] = details
    return ET.Element("Action", attrs)


def main_sequence(root: ET.Element) -> ET.Element:
    bt = root.find("BehaviorTree")
    if bt is None or len(bt) != 1 or bt[0].tag != "Sequence":
        raise RuntimeError("Unexpected BT structure")
    return bt[0]


def write_tree(tree: ET.ElementTree, path: Path) -> None:
    ET.indent(tree, space="    ")
    tree.write(path, encoding="unicode", xml_declaration=False)


def parse_bt(path: Path) -> ET.ElementTree:
    # Some challenge BTs contain commented prompt text that is not accepted by
    # ElementTree's default parser. Dropping comments preserves executable XML.
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=False))
    text = path.read_text().replace("<__media__>", "&lt;__media__&gt;")
    return ET.ElementTree(ET.fromstring(text, parser=parser))


def instrument_modular(out_dir: Path) -> None:
    for filename, capability in MODULAR.items():
        tree = parse_bt(BT_DIR / filename)
        seq = main_sequence(tree.getroot())
        seq.insert(0, trace("first_bt_action_start", capability, "modular"))
        seq.append(trace("last_bt_action_finish", capability, "modular"))
        write_tree(tree, out_dir / f"runtime_{filename}")


def instrument_capability_bt_fragments(out_dir: Path) -> None:
    for capability_key, (filename, capability_label) in CAPABILITIES.items():
        tree = parse_bt(BT_DIR / filename)
        seq = main_sequence(tree.getroot())
        seq.insert(0, trace("capability_executable", capability_label, "bt"))
        seq.insert(1, trace("first_bt_action_start", capability_label, "bt"))
        seq.append(trace("last_bt_action_finish", capability_label, "bt"))
        seq.append(trace("capability_finished", capability_label, "bt"))
        seq.append(trace("transition_to_next", capability_label, "bt"))
        write_tree(tree, out_dir / f"runtime_bt_{capability_key}.xml")


def write_runtime_params(out_dir: Path) -> None:
    params = (PACKAGE / "config" / "params.yaml").read_text()
    for filename in MODULAR:
        params = params.replace(
            f"bt_name: '{filename}'",
            f"bt_name: 'runtime_instrumented/runtime_{filename}'",
        )
    (out_dir / "runtime_params.yaml").write_text(params)


def top_level_action(node: ET.Element, node_id: str, attr: str | None = None, value: str | None = None) -> bool:
    if node.tag != "Action" or node.get("ID") != node_id:
        return False
    if attr is None:
        return True
    return node.get(attr) == value


def find_seat_spans(children: list[ET.Element]) -> list[tuple[int, int, str]]:
    spans = []
    for i, child in enumerate(children):
        if top_level_action(child, "Speak", "say_text", "I'll find you a seat"):
            end = i
            for j in range(i + 1, len(children)):
                if top_level_action(children[j], "SetTorsoHeight", "height", "0.3"):
                    end = j
                    break
            spans.append((i, end, "Find Seat"))
    return spans


def grab_bag_span(children: list[ET.Element]) -> tuple[int, int, str] | None:
    start = None
    for i, child in enumerate(children):
        if top_level_action(child, "GetModelPath", "model", "best26.pt"):
            start = i
            break
    if start is None:
        return None
    end = start
    for j in range(start, len(children)):
        if top_level_action(children[j], "SwitchYoloModel", "model", "yolo11n.pt"):
            end = j
            break
    return (start, end, "Grab Bag")


def transport_bag_span(children: list[ET.Element]) -> tuple[int, int, str] | None:
    for i, child in enumerate(children):
        if child.tag == "Action" and child.get("ID") == "InitReceptionist" and "follow_ready_wp" in child.attrib:
            return (i, len(children) - 1, "Transport Bag")
    return None


def instrument_span(seq: ET.Element, start: int, end: int, capability: str) -> None:
    # Insert from the end so the original span indices remain valid.
    seq.insert(end + 1, trace("transition_to_next", capability, "monolithic"))
    seq.insert(end + 1, trace("capability_finished", capability, "monolithic"))
    seq.insert(end + 1, trace("last_bt_action_finish", capability, "monolithic"))
    seq.insert(start, trace("first_bt_action_start", capability, "monolithic"))
    seq.insert(start, trace("capability_executable", capability, "monolithic"))


def instrument_monolithic(out_dir: Path) -> None:
    tree = parse_bt(BT_DIR / "hri_challenge.xml")
    seq = main_sequence(tree.getroot())
    children = list(seq)

    spans: list[tuple[int, int, str]] = []
    spans.extend(find_seat_spans(children))
    grab = grab_bag_span(children)
    if grab:
        spans.append(grab)
    transport = transport_bag_span(children)
    if transport:
        spans.append(transport)

    for start, end, capability in sorted(spans, reverse=True):
        instrument_span(seq, start, end, capability)

    write_tree(tree, out_dir / "runtime_hri_challenge.xml")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(BT_DIR / "runtime_instrumented"))
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    instrument_monolithic(out_dir)
    instrument_modular(out_dir)
    instrument_capability_bt_fragments(out_dir)
    write_runtime_params(out_dir)
    print(f"Generated runtime-instrumented BT XML in {out_dir}")
    print(f"Generated modular runtime params in {out_dir / 'runtime_params.yaml'}")


if __name__ == "__main__":
    main()
