Perfect — below is the **exact, production-ready MCP tool schema set** for the **BrainDrive Markdown MCP Server**.

This is intentionally:

* **Strict** (no ambiguous fields)
* **Deterministic**
* **Machine-verifiable**
* **Aligned 1:1 with the build plan**

You can treat this as **the contract**.
If a tool is not defined here, the MCP does not support it.

---

# BrainDrive Markdown MCP

## Tool Schemas (Authoritative)

> **Spec Version:** v0.3
> **Applies to:** Markdown MCP Server
> **Format:** MCP-compatible JSON Schema (OpenAI / Anthropic compatible)

---

## Global Conventions

### Path Rules (applies to all tools)

* `path` is **relative** to `BRAINDRIVE_LIBRARY_PATH`
* No `..`
* No absolute paths
* Markdown files only (`.md`, `.markdown`, `.mdx`)

### Response Guarantees

* All tools are **pure** unless stated otherwise
* Write operations return `git_commit_sha`
* Errors never cause partial writes

---

## 1. Read Operations

### `read_markdown`

```json
{
  "name": "read_markdown",
  "description": "Read a markdown file from the BrainDrive Library. Read-only operation.",
  "input_schema": {
    "type": "object",
    "required": ["path"],
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path to a markdown file inside the Library"
      }
    },
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "required": ["content", "metadata"],
    "properties": {
      "content": { "type": "string" },
      "metadata": {
        "type": "object",
        "required": ["size", "last_modified", "git_commit"],
        "properties": {
          "size": { "type": "integer" },
          "last_modified": { "type": "string", "format": "date-time" },
          "git_commit": { "type": "string" }
        }
      }
    }
  }
}
```

---

## 2. Listing & Search

### `list_markdown_files`

```json
{
  "name": "list_markdown_files",
  "description": "List markdown files and folders under a directory.",
  "input_schema": {
    "type": "object",
    "required": ["path"],
    "properties": {
      "path": { "type": "string" },
      "recursive": { "type": "boolean", "default": false }
    },
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "required": ["files", "folders"],
    "properties": {
      "files": {
        "type": "array",
        "items": { "type": "string" }
      },
      "folders": {
        "type": "array",
        "items": { "type": "string" }
      }
    }
  }
}
```

---

### `search_markdown`

```json
{
  "name": "search_markdown",
  "description": "Search for text across markdown files.",
  "input_schema": {
    "type": "object",
    "required": ["query"],
    "properties": {
      "query": { "type": "string" },
      "path": { "type": "string" }
    },
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "required": ["results"],
    "properties": {
      "results": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["path", "matches"],
          "properties": {
            "path": { "type": "string" },
            "matches": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["line", "snippet"],
                "properties": {
                  "line": { "type": "integer" },
                  "snippet": { "type": "string" }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

---

## 3. Preview & Diff

### `preview_markdown_change`

```json
{
  "name": "preview_markdown_change",
  "description": "Generate a diff preview for a proposed markdown change without writing.",
  "input_schema": {
    "type": "object",
    "required": ["path", "operation"],
    "properties": {
      "path": { "type": "string" },
      "operation": {
        "type": "object",
        "required": ["type", "content"],
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "append",
              "prepend",
              "replace_section",
              "insert_before",
              "insert_after"
            ]
          },
          "target": {
            "type": "string",
            "description": "Markdown heading or anchor (required for section-based ops)"
          },
          "content": { "type": "string" }
        },
        "additionalProperties": false
      }
    },
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "required": ["diff", "summary", "risk_level"],
    "properties": {
      "diff": { "type": "string" },
      "summary": { "type": "string" },
      "risk_level": {
        "type": "string",
        "enum": ["low", "medium", "high"]
      }
    }
  }
}
```

---

## 4. Write & Edit Operations

### `write_markdown`

```json
{
  "name": "write_markdown",
  "description": "Create or overwrite a markdown file. Requires human approval upstream.",
  "input_schema": {
    "type": "object",
    "required": ["path", "content"],
    "properties": {
      "path": { "type": "string" },
      "content": { "type": "string" }
    },
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "required": ["success", "git_commit_sha"],
    "properties": {
      "success": { "type": "boolean" },
      "git_commit_sha": { "type": "string" }
    }
  }
}
```

---

### `edit_markdown`

```json
{
  "name": "edit_markdown",
  "description": "Apply a structured edit to an existing markdown file.",
  "input_schema": {
    "type": "object",
    "required": ["path", "operation"],
    "properties": {
      "path": { "type": "string" },
      "operation": {
        "type": "object",
        "required": ["type", "content"],
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "append",
              "prepend",
              "replace_section",
              "insert_before",
              "insert_after"
            ]
          },
          "target": {
            "type": "string",
            "description": "Required for replace/insert operations"
          },
          "content": { "type": "string" }
        },
        "additionalProperties": false
      }
    },
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "required": ["success", "git_commit_sha"],
    "properties": {
      "success": { "type": "boolean" },
      "git_commit_sha": { "type": "string" }
    }
  }
}
```

---

## 5. Delete Operations

### `delete_markdown`

```json
{
  "name": "delete_markdown",
  "description": "Delete a markdown file. Requires explicit confirmation.",
  "input_schema": {
    "type": "object",
    "required": ["path", "confirm"],
    "properties": {
      "path": { "type": "string" },
      "confirm": {
        "type": "boolean",
        "description": "Must be true to proceed"
      }
    },
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "required": ["success", "git_commit_sha"],
    "properties": {
      "success": { "type": "boolean" },
      "git_commit_sha": { "type": "string" }
    }
  }
}
```

---

## 6. Activity Log

### `get_markdown_activity_log`

```json
{
  "name": "get_markdown_activity_log",
  "description": "Retrieve the markdown operation activity log.",
  "input_schema": {
    "type": "object",
    "properties": {
      "limit": { "type": "integer", "default": 50 }
    },
    "additionalProperties": false
  },
  "output_schema": {
    "type": "object",
    "required": ["entries"],
    "properties": {
      "entries": {
        "type": "array",
        "items": {
          "type": "object",
          "required": [
            "timestamp",
            "operation",
            "path",
            "summary",
            "git_commit_sha"
          ],
          "properties": {
            "timestamp": { "type": "string", "format": "date-time" },
            "operation": { "type": "string" },
            "path": { "type": "string" },
            "summary": { "type": "string" },
            "git_commit_sha": { "type": "string" }
          }
        }
      }
    }
  }
}
```

---

## 7. Hard Guarantees (Contractual)

The MCP **must** guarantee:

* ❌ No tool writes without explicit call
* ❌ No implicit edits
* ❌ No partial application
* ✅ Preview == execution result
* ✅ Every mutation → git commit
* ✅ Every mutation → activity log entry

If any of these are violated, the MCP is considered **incorrectly implemented**.

