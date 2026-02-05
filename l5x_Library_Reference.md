# Python `l5x` Library — Complete Data Extraction Reference

> **Library:** `l5x` (pip install l5x)  
> **Purpose:** Read, modify, and write RSLogix 5000 / Studio 5000 L5X project files  
> **Source:** Pure Python, uses `xml.etree.ElementTree` under the hood  

---

## Quick Start

```python
import l5x

project = l5x.Project('my_project.L5X')
```

Everything hangs off the `Project` object. From there you access the controller, programs, modules, and all their tags.

---

## 1. Project-Level Data

| Access Path | Data Returned | Read/Write |
|---|---|---|
| `project.controller` | Controller object (the PLC itself) | — |
| `project.programs` | Dict-like container of all Programs | — |
| `project.programs.names` | List of all program names (strings) | Read |
| `project.modules` | Dict-like container of all I/O Modules | — |
| `project.modules.names` | List of all module names (strings) | Read |
| `project.write('output.L5X')` | Saves the (modified) project to a new file | — |

---

## 2. Controller Scope (Global Tags)

The controller is a **Scope** — it holds the controller-scoped (global) tags.

| Access Path | Data Returned | Read/Write |
|---|---|---|
| `project.controller.tags` | Dict-like container of all controller-scoped tags | — |
| `project.controller.tags.names` | List of all controller-scoped tag names | Read |
| `project.controller.comm_path` | Communication path string (e.g., `"AB_ETH-1, 192.168.1.1, 1, 0"`) | Read/Write |
| `project.controller.snn` | Safety Network Number (hex string, safety controllers only) | Read/Write |

---

## 3. Programs & Program-Scoped Tags

Each program is also a **Scope** with its own set of tags.

| Access Path | Data Returned | Read/Write |
|---|---|---|
| `project.programs['MainProgram']` | A single Program (Scope) object | — |
| `project.programs['MainProgram'].tags` | Dict-like container of program-scoped tags | — |
| `project.programs['MainProgram'].tags.names` | List of tag names in that program | Read |

```python
# Iterate all programs and their tags
for prog_name in project.programs.names:
    program = project.programs[prog_name]
    for tag_name in program.tags.names:
        tag = program.tags[tag_name]
        print(f"{prog_name}/{tag_name}: {tag.data_type}")
```

---

## 4. Tags — The Core Data Object

Every tag (controller-scoped or program-scoped) exposes these properties:

### 4.1 Base Tag Properties

| Property | Data Returned | Read/Write |
|---|---|---|
| `tag.data_type` | Data type string (e.g., `"DINT"`, `"REAL"`, `"TIMER"`, `"AB:E300:I:3"`, or UDT name) | Read |
| `tag.description` | Top-level tag description / comment (string or `None`) | Read/Write |
| `tag.value` | Current tag value (type depends on data type — see below) | Read/Write |

### 4.2 Alias Tags

If a tag is an alias, you get an `AliasTag` object instead of a regular `Tag`:

| Property | Data Returned | Read/Write |
|---|---|---|
| `alias_tag.alias_for` | The target tag/address this alias points to (string) | Read/Write |
| `alias_tag.description` | Alias tag description (string or `None`) | Read/Write |

```python
tag = project.controller.tags['MyAlias']
if isinstance(tag, l5x.tag.AliasTag):
    print(f"Alias for: {tag.alias_for}")
```

### 4.3 Consumed Tags

Tags that consume data from a producer controller:

| Property | Data Returned | Read/Write |
|---|---|---|
| `tag.producer` | Name of the producing controller (string) | Read/Write |
| `tag.remote_tag` | Name of the produced tag on the remote controller (string) | Read/Write |

---

## 5. Tag Values by Data Type

### 5.1 Atomic Types

| Data Type | `tag.value` Returns | Value Range |
|---|---|---|
| `BOOL` | `int` (0 or 1) | 0–1 |
| `SINT` | `int` | −128 to 127 |
| `INT` | `int` | −32,768 to 32,767 |
| `DINT` | `int` | −2,147,483,648 to 2,147,483,647 |
| `REAL` | `float` | Standard IEEE 754 |

### 5.2 Integer Bit Access

Any integer type (SINT, INT, DINT) supports bit-level access:

| Access Path | Data Returned | Read/Write |
|---|---|---|
| `tag[bit_number].value` | Individual bit value (0 or 1) | Read/Write |
| `tag[bit_number].description` | Bit-level comment/description (string or `None`) | Read/Write |
| `len(tag)` | Number of bits (8, 16, or 32) | Read |

```python
# Read bit 5 of a DINT tag
tag = project.controller.tags['MyDINT']
print(tag[5].value)         # 0 or 1
print(tag[5].description)   # Bit-level comment
```

### 5.3 Structures (UDTs and Built-in Types like TIMER, COUNTER, PID)

| Access Path | Data Returned | Read/Write |
|---|---|---|
| `tag.names` | List of member names (e.g., `['PRE', 'ACC', 'EN', 'TT', 'DN']` for TIMER) | Read |
| `tag.value` | Dict of all member values `{'PRE': 5000, 'ACC': 0, ...}` | Read/Write |
| `tag['MemberName'].value` | Individual member value | Read/Write |
| `tag['MemberName'].description` | Member-level comment | Read/Write |
| `tag['MemberName'].names` | Sub-member names (for nested structures) | Read |

```python
# Access a TIMER tag
timer = project.controller.tags['DelayTimer']
print(timer.names)           # ['PRE', 'ACC', 'EN', 'TT', 'DN']
print(timer['PRE'].value)    # 5000
print(timer.value)           # {'PRE': 5000, 'ACC': 0, 'EN': 0, 'TT': 0, 'DN': 0}

# Access a UDT
udt = project.controller.tags['MyMotor']
print(udt.names)             # ['Running', 'Faulted', 'Speed', ...]
print(udt['Speed'].value)    # 1750.0
```

### 5.4 Arrays

| Access Path | Data Returned | Read/Write |
|---|---|---|
| `tag.shape` | Tuple of dimensions, e.g., `(10,)` or `(3, 4)` | Read/Write* |
| `tag.value` | List of all element values | Read/Write |
| `tag[index].value` | Single element value | Read/Write |
| `tag[index].description` | Element-level comment | Read/Write |

\* Setting `.shape` resizes the array (top-level arrays only, not UDT members).

```python
# Access array elements
arr = project.controller.tags['Temperatures']
print(arr.shape)       # (20,)
print(arr[0].value)    # 72.5
print(arr.value)       # [72.5, 68.3, 71.0, ...]

# Multidimensional
arr2d = project.controller.tags['Matrix']
print(arr2d.shape)     # (3, 4)
print(arr2d[1][2].value)

# Resize an array
arr.shape = (30,)      # Grows from 20 to 30 elements
```

### 5.5 Arrays of Structures

Arrays of UDTs combine both access patterns:

```python
motors = project.controller.tags['MotorArray']
print(motors.shape)                  # (10,)
print(motors[0].names)               # ['Running', 'Speed', ...]
print(motors[0]['Speed'].value)      # 1750.0
print(motors[0]['Speed'].description)  # "Motor 1 speed setpoint"
```

---

## 6. I/O Modules

| Access Path | Data Returned | Read/Write |
|---|---|---|
| `project.modules.names` | List of all module names | Read |
| `project.modules['ModuleName']` | A single Module object | — |
| `module.inhibited` | Whether the module is inhibited (`True`/`False`) | Read/Write |
| `module.snn` | Safety Network Number (safety modules only) | Read/Write |
| `module.ports` | Dict-like container of Port objects (keyed by integer ID) | — |
| `module.ports[port_id]` | A single Port object | — |

### 6.1 Module Ports

| Access Path | Data Returned | Read/Write |
|---|---|---|
| `port.type` | Port type string (e.g., `"ICP"`, `"Ethernet"`) | Read |
| `port.address` | Port address (e.g., `"192.168.1.10"`, `"2"`) | Read/Write |
| `port.nat_address` | NAT address (if configured) | Read/Write |
| `port.snn` | Safety Network Number (safety ports only) | Read/Write |

```python
# List all modules and their port addresses
for mod_name in project.modules.names:
    module = project.modules[mod_name]
    print(f"\nModule: {mod_name} (inhibited={module.inhibited})")
    for port_id in module.ports.names:
        port = module.ports[port_id]
        print(f"  Port {port_id}: type={port.type}, address={port.address}")
```

---

## 7. Descriptions / Comments at Every Level

The library provides access to descriptions (comments) at every level of the tag hierarchy:

| Level | Access Path | Example |
|---|---|---|
| **Tag-level** | `tag.description` | `"Main conveyor motor"` |
| **Structure member** | `tag['MemberName'].description` | `"Motor running feedback"` |
| **Array element** | `tag[index].description` | `"Zone 1 temperature"` |
| **Integer bit** | `tag[bit].description` | `"Pump 1 running status"` |
| **Nested member** | `tag['Struct']['SubMember'].description` | `"Nested comment"` |
| **Alias tag** | `alias_tag.description` | `"Points to conveyor speed"` |

All descriptions are **Read/Write** — set to `None` to delete.

---

## 8. Complete Data Extraction Example

```python
import l5x

project = l5x.Project('XFERSYS.L5X')

# ---- CONTROLLER-SCOPED (GLOBAL) TAGS ----
print("=== Controller Tags ===")
for name in project.controller.tags.names:
    tag = project.controller.tags[name]
    
    # Check if alias
    if isinstance(tag, l5x.tag.AliasTag):
        print(f"  ALIAS: {name} -> {tag.alias_for}")
        if tag.description:
            print(f"    Description: {tag.description}")
        continue
    
    print(f"  TAG: {name}  Type: {tag.data_type}  Desc: {tag.description}")
    
    # For structures, list members
    try:
        for member in tag.names:
            member_obj = tag[member]
            print(f"    .{member} = {member_obj.value}  ({member_obj.description})")
    except (TypeError, AttributeError):
        # Not a structure, just print value
        try:
            print(f"    Value: {tag.value}")
        except:
            pass

# ---- PROGRAM-SCOPED TAGS ----
print("\n=== Programs ===")
for prog_name in project.programs.names:
    program = project.programs[prog_name]
    print(f"\nProgram: {prog_name}")
    for name in program.tags.names:
        tag = program.tags[name]
        if isinstance(tag, l5x.tag.AliasTag):
            print(f"  ALIAS: {name} -> {tag.alias_for}")
        else:
            print(f"  TAG: {name}  Type: {tag.data_type}")

# ---- I/O MODULES ----
print("\n=== Modules ===")
for mod_name in project.modules.names:
    module = project.modules[mod_name]
    print(f"\nModule: {mod_name}  Inhibited: {module.inhibited}")
    for port_id in module.ports.names:
        port = module.ports[port_id]
        print(f"  Port {port_id}: Type={port.type}  Address={port.address}")
```

---

## 9. Summary: All Extractable Data Points

| Category | Data Point | Access Method |
|---|---|---|
| **Project** | Full XML document | `project.doc` (ElementTree root) |
| **Controller** | Communication path | `project.controller.comm_path` |
| | Safety Network Number | `project.controller.snn` |
| | All global tag names | `project.controller.tags.names` |
| **Programs** | All program names | `project.programs.names` |
| | Program-scoped tag names | `project.programs[name].tags.names` |
| **Tags** | Data type | `tag.data_type` |
| | Description / comment | `tag.description` |
| | Current value | `tag.value` |
| | Alias target | `alias_tag.alias_for` |
| | Consumed tag producer | `tag.producer` |
| | Consumed tag remote name | `tag.remote_tag` |
| **Structures** | Member names | `tag.names` |
| | Member values | `tag['member'].value` |
| | Member comments | `tag['member'].description` |
| | Nested member access | `tag['member']['sub'].value` |
| **Arrays** | Dimensions / shape | `tag.shape` |
| | Element values | `tag[i].value` |
| | Element comments | `tag[i].description` |
| | Bulk values (list) | `tag.value` |
| | Resize | `tag.shape = (new_size,)` |
| **Integers** | Bit-level value | `tag[bit].value` |
| | Bit-level comment | `tag[bit].description` |
| | Bit width | `len(tag)` |
| **Modules** | All module names | `project.modules.names` |
| | Inhibit status | `module.inhibited` |
| | Safety Network Number | `module.snn` |
| | Port type | `port.type` |
| | Port address (IP or slot) | `port.address` |
| | Port NAT address | `port.nat_address` |
| | Port SNN | `port.snn` |

---

## 10. Limitations & Notes

- **No rung logic access:** The library does not parse ladder logic, function blocks, or structured text. It accesses tags and modules only. To scan program logic for tag references, you'd need to parse the raw XML from the L5X file directly.
- **Encoded source protection:** If the L5X was saved with "Encode Source Protected Content" enabled, decorated data won't be accessible and you'll get a `RuntimeError`.
- **No Add-On Instructions (AOIs):** The library doesn't expose AOI definitions as first-class objects.
- **No Tasks / Routines:** Task configuration and routine structure aren't directly accessible through the API.
- **No trend / alarm configuration:** These project elements aren't exposed.
- **CDATA handling:** The library automatically manages CDATA section conversion during read/write — you don't need to worry about it.
- **Multilanguage support:** Comments/descriptions support localized languages if the project uses them (handled via `CurrentLanguage` attribute).
- **All access is read/write:** You can modify any value and call `project.write()` to save changes. This makes it useful for bulk tag edits, not just data extraction.
