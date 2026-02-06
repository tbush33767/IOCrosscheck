"""Matching strategies for the IO Crosscheck rule cascade."""
from __future__ import annotations

from io_crosscheck.models import (
    PLCTag, IODevice, MatchResult, RecordType, AddressFormat,
    Classification, Confidence, TagCategory,
)
from io_crosscheck.normalizers import (
    normalize_tag, normalize_address, extract_rack_base, extract_enet_device,
)
from io_crosscheck.classifiers import is_spare, is_enet_device_tag


class BaseStrategy:
    """Base class for all matching strategies."""
    strategy_id: int = 0
    name: str = ""

    def match(self, io_device: IODevice, plc_tags: list[PLCTag]) -> MatchResult | None:
        """Attempt to match an IO device against PLC tags.

        Returns a MatchResult if a match is found, None otherwise.
        """
        raise NotImplementedError


class DirectCLXAddressMatch(BaseStrategy):
    """Strategy 1: Direct Address Match for ControlLogix rack IO."""
    strategy_id = 1
    name = "Direct CLX Address Match"

    def match(self, io_device: IODevice, plc_tags: list[PLCTag]) -> MatchResult | None:
        if io_device.address_format != AddressFormat.CLX:
            return None
        if not io_device.plc_address:
            return None

        norm_addr = normalize_address(io_device.plc_address)

        for tag in plc_tags:
            if tag.record_type != RecordType.COMMENT:
                continue
            if not tag.specifier:
                continue
            if normalize_address(tag.specifier) == norm_addr:
                # Address matches — check if device name also matches
                io_base = normalize_tag(io_device.io_tag) if io_device.io_tag else ""
                io_dev_base = normalize_tag(io_device.device_tag) if io_device.device_tag else ""
                plc_desc = tag.description.strip().lower() if tag.description else ""

                name_matches = (
                    (plc_desc and (plc_desc == io_base or plc_desc == io_dev_base))
                    or not plc_desc
                    or not io_base
                )

                if name_matches:
                    return MatchResult(
                        io_device=io_device,
                        plc_tag=tag,
                        strategy_id=self.strategy_id,
                        confidence=Confidence.EXACT,
                        classification=Classification.BOTH,
                        audit_trail=[
                            f"Strategy 1: Direct CLX Address Match",
                            f"IO address '{io_device.plc_address}' matches PLC COMMENT specifier '{tag.specifier}' (case-insensitive)",
                            f"PLC description: '{tag.description}', IO tag: '{io_device.io_tag}', Device tag: '{io_device.device_tag}'",
                        ],
                    )
                else:
                    return MatchResult(
                        io_device=io_device,
                        plc_tag=tag,
                        strategy_id=self.strategy_id,
                        confidence=Confidence.EXACT,
                        classification=Classification.CONFLICT,
                        conflict_flag=True,
                        audit_trail=[
                            f"Strategy 1: Direct CLX Address Match — CONFLICT",
                            f"IO address '{io_device.plc_address}' matches PLC COMMENT specifier '{tag.specifier}'",
                            f"BUT device names differ: IO='{io_device.device_tag}' vs PLC='{tag.description}'",
                        ],
                    )
        return None


class PLC5RackAddressMatch(BaseStrategy):
    """Strategy 2: PLC5 Rack Address Match."""
    strategy_id = 2
    name = "PLC5 Rack Address Match"

    def match(self, io_device: IODevice, plc_tags: list[PLCTag]) -> MatchResult | None:
        if io_device.address_format != AddressFormat.PLC5:
            return None
        if not io_device.plc_address:
            return None

        # Extract the base tag name from the PLC5 address (everything before the dot)
        addr = io_device.plc_address.strip()
        dot_pos = addr.find(".")
        if dot_pos > 0:
            addr_base = addr[:dot_pos].lower()
        else:
            addr_base = addr.lower()

        for tag in plc_tags:
            if tag.record_type != RecordType.TAG:
                continue
            tag_name_lower = tag.name.strip().lower()
            if tag_name_lower == addr_base:
                return MatchResult(
                    io_device=io_device,
                    plc_tag=tag,
                    strategy_id=self.strategy_id,
                    confidence=Confidence.EXACT,
                    classification=Classification.BOTH,
                    audit_trail=[
                        f"Strategy 2: PLC5 Rack Address Match",
                        f"IO address base '{addr_base}' matches PLC TAG name '{tag.name}' (case-insensitive)",
                    ],
                )
        return None


class ENetModuleTagExtraction(BaseStrategy):
    """Strategy 4: EtherNet/IP Module Tag Extraction."""
    strategy_id = 4
    name = "ENet Module Tag Extraction"

    def match(self, io_device: IODevice, plc_tags: list[PLCTag]) -> MatchResult | None:
        io_dev_tag = io_device.device_tag.strip() if io_device.device_tag else ""
        io_io_tag = io_device.io_tag.strip() if io_device.io_tag else ""
        if not io_dev_tag and not io_io_tag:
            return None

        io_dev_lower = io_dev_tag.lower()
        io_io_lower = io_io_tag.lower()

        for tag in plc_tags:
            if tag.record_type != RecordType.TAG:
                continue
            device_id = extract_enet_device(tag.name)
            if device_id is None:
                continue
            device_id_lower = device_id.lower()
            if device_id_lower == io_dev_lower or device_id_lower == io_io_lower:
                return MatchResult(
                    io_device=io_device,
                    plc_tag=tag,
                    strategy_id=self.strategy_id,
                    confidence=Confidence.EXACT,
                    classification=Classification.BOTH,
                    audit_trail=[
                        f"Strategy 4: ENet Module Tag Extraction",
                        f"Extracted device '{device_id}' from PLC TAG '{tag.name}'",
                        f"Matches IO device tag '{io_device.device_tag}' (case-insensitive)",
                    ],
                )
        return None


class TagNameNormalizationMatch(BaseStrategy):
    """Strategy 5: Tag Name Normalization Match."""
    strategy_id = 5
    name = "Tag Name Normalization Match"

    def match(self, io_device: IODevice, plc_tags: list[PLCTag]) -> MatchResult | None:
        io_tag_norm = normalize_tag(io_device.io_tag) if io_device.io_tag else ""
        dev_tag_norm = normalize_tag(io_device.device_tag) if io_device.device_tag else ""

        if not io_tag_norm and not dev_tag_norm:
            return None

        candidates = set()
        if io_tag_norm:
            candidates.add(io_tag_norm)
        if dev_tag_norm:
            candidates.add(dev_tag_norm)

        for tag in plc_tags:
            # Match against PLC TAG base_name or COMMENT description
            plc_names: list[str] = []
            if tag.base_name:
                plc_names.append(normalize_tag(tag.base_name))
            if tag.description:
                plc_names.append(tag.description.strip().lower())

            for plc_name in plc_names:
                if not plc_name:
                    continue
                # Exact match only — no substring matching
                if plc_name in candidates:
                    return MatchResult(
                        io_device=io_device,
                        plc_tag=tag,
                        strategy_id=self.strategy_id,
                        confidence=Confidence.HIGH,
                        classification=Classification.BOTH,
                        audit_trail=[
                            f"Strategy 5: Tag Name Normalization Match",
                            f"Normalized IO tag(s) {candidates} matched PLC name '{plc_name}'",
                            f"IO tag: '{io_device.io_tag}', Device tag: '{io_device.device_tag}'",
                            f"PLC source: {tag.record_type.value} '{tag.name}' (description='{tag.description}', base_name='{tag.base_name}')",
                        ],
                    )
        return None


class MatchingEngine:
    """Executes matching strategies in priority order."""

    def __init__(self) -> None:
        self.strategies: list[BaseStrategy] = [
            DirectCLXAddressMatch(),
            PLC5RackAddressMatch(),
            ENetModuleTagExtraction(),
            TagNameNormalizationMatch(),
        ]

    def run(
        self, io_devices: list[IODevice], plc_tags: list[PLCTag]
    ) -> list[MatchResult]:
        """Run the full matching cascade and return classification results."""
        results: list[MatchResult] = []
        matched_plc_tags: set[int] = set()  # track by source_line

        # Phase 1: classify each IO device
        for io_dev in io_devices:
            # Check for spare points first
            if is_spare(io_dev.io_tag):
                results.append(MatchResult(
                    io_device=io_dev,
                    classification=Classification.SPARE,
                    audit_trail=[f"IO tag '{io_dev.io_tag}' identified as spare — excluded from matching"],
                ))
                continue

            # Run strategies in cascade order
            matched = False
            for strategy in self.strategies:
                result = strategy.match(io_dev, plc_tags)
                if result is not None:
                    results.append(result)
                    if result.plc_tag and result.plc_tag.source_line:
                        matched_plc_tags.add(result.plc_tag.source_line)
                    matched = True
                    break

            if not matched:
                results.append(MatchResult(
                    io_device=io_dev,
                    classification=Classification.IO_LIST_ONLY,
                    audit_trail=[
                        f"No matching strategy found for IO device",
                        f"IO tag: '{io_dev.io_tag}', Device tag: '{io_dev.device_tag}', Address: '{io_dev.plc_address}'",
                        f"Strategies evaluated: {[s.name for s in self.strategies]}",
                    ],
                ))

        # Phase 2: identify PLC-only tags (ENet devices with no IO List match)
        for tag in plc_tags:
            if tag.source_line in matched_plc_tags:
                continue
            if is_enet_device_tag(tag) and tag.record_type == RecordType.TAG:
                results.append(MatchResult(
                    plc_tag=tag,
                    classification=Classification.PLC_ONLY,
                    audit_trail=[
                        f"PLC TAG '{tag.name}' has no matching IO List device",
                        f"Classified as PLC Only (ENet device)",
                    ],
                ))

        return results
