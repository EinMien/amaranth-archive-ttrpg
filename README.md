# amaranth-archive-ttrpg

**Asynchronous TTRPG Campaign Engine, Multi-Tenant State Manager & Preference Matrix**
**Developed for Lovable_Sylveon**

## System Architecture

The `amaranth-archive-ttrpg` engine is designed to handle complex, asynchronous game states across multiple overlapping contexts (Guilds, Direct Messages, and Shared Parties). It leverages a robust schema architecture to support multi-tenant TTRPG interactions without the overhead of heavy RDBMS frameworks, utilizing lightweight `json` models mapped dynamically to Discord views and models.

## Data Architecture & Unique Instance Tracking

### 32-bit FNV-1a Hashing Strategy
In many TTRPG systems, differentiating between identical items (e.g., two standard swords where one has been secretly cursed) is a significant architectural challenge. 

This engine solves this issue elegantly using a custom implementation of the **32-bit FNV-1a hash algorithm** to track the lifecycle of unique inventory instances. 

```python
def generate_uid(data):
    hash_val = 0x811c9dc5
    for char in data:
        hash_val ^= ord(char)
        hash_val = (hash_val * 0x01000193) & 0xffffffff
    return hex(hash_val)[2:]
```
This ensures high collision-resistance and fast execution when modifying item characteristics without relying on external UUID libraries or auto-incrementing SQL primary keys.

### Multi-Tenant Relational State Model
The backend implements strict scope-isolation boundaries. Data context operates relationally across:
- **Global Guild State**
- **DM Target Scopes** (Global, Party, Personal)
- **Character Rosters**
- **Shared Party Vaults**

This isolation prevents data-leakage during active campaigns (e.g. ensuring a player in "Guild A" does not accidentally access their vault from "Guild B").

## Defensive API Engineering

### Recursive Embed Chunking
Discord's API strictly enforces payload limits: 1,024 characters per embed field, and 6,000 characters per total embed. When processing user-generated TTRPG content, naïve rendering crashes with HTTP 400 Bad Request errors.

This engine features a defensive `add_chunked_field()` algorithm. It recursively splits excessive text blocks across multiple embed fields, protecting the bot from malicious copypasta API floods and ensuring stable data presentation for extensive campaign logs.
