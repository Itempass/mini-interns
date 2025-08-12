## Workflow Templates

Put template files here as `.json`. The filename (without `.json`) is the template `id` shown in the UI.

### Required fields
- **name**: string
- **description**: string

### Optional: prebuilt workflow import
- **workflow_import**: object
  - Paste the exact JSON you get from exporting a workflow (GET `/api/workflows/{uuid}/export`).
  - The importer will create steps and a trigger and remap internal UUID references.

Notes about imports:
- Supported step types: `custom_llm`, `custom_agent`, `stop_checker`.
- `steps[*].uuid` must be present; used for remapping.
- For `stop_checker`, `step_to_check_uuid` should reference a step UUID from the exported data.

### Chat behavior (first turn)
- **starter_chat**: object
  - **mode**: `"auto"` | `"prompt"`
  - **message**: string
  - **responses**: optional array of `{ label: string, message: string }` (used only when `mode` is `"prompt"`)

Behavior:
- `mode = "auto"`: the message is auto-sent as the user's first message to start the conversation.
- `mode = "prompt"`: the message shows as the assistant's first message with quick-reply buttons from `responses`.

### Minimal examples

Auto-send starter message:
```json
{
  "name": "Repetitive Email Drafter",
  "description": "Creates drafts for repetitive emails.",
  "starter_chat": {
    "mode": "auto",
    "message": "Let's build a repetitive email drafter workflow."
  }
}
```

Prompt with quick replies:
```json
{
  "name": "Email Labeler",
  "description": "Labels incoming emails.",
  "starter_chat": {
    "mode": "prompt",
    "message": "How would you like to set up email labeling?",
    "responses": [
      { "label": "Use defaults", "message": "Set label rules automatically." },
      { "label": "I'll configure rules", "message": "Guide me to define label rules." }
    ]
  }
}
```

With prebuilt workflow import:
```json
{
  "name": "Email Labeler (Prebuilt)",
  "description": "Prebuilt labeling workflow.",
  "workflow_import": {
    "name": "Email Labeler",
    "description": "…",
    "steps": [
      { "uuid": "11111111-1111-1111-1111-111111111111", "type": "custom_llm", "name": "Decide Label", "model": "google/gemini-2.5-flash", "system_prompt": "…" }
    ],
    "trigger": { "filter_rules": { "folder_names": ["INBOX"] } }
  },
  "starter_chat": { "mode": "prompt", "message": "Review the steps or start labeling.", "responses": [ { "label": "Proceed", "message": "Looks good, proceed." } ] }
}
```


