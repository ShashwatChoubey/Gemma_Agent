Prerequisites
- Python 3.8+
- Grafana instance with Prometheus datasource
- Google AI API key
- Windows/Node Exporter configured

1. Clone the repo
2. Install dependencies: `pip install -r requirements.txt`
3. Configure `.env` with your API keys
4. Run: `python agent.py`

This project uses Google's Gemma AI as an intelligent agent to query Grafana datasources and present monitoring results in natural language. The system bridges the gap between complex monitoring queries and user-friendly conversations.

 System Flow
The architecture follows a straightforward pipeline:

User → Agent (Gemma) → Backend (Query Builder + Executor) → Grafana/Prometheus → Result → Gemma (Answer)

 Component Breakdown:
Gemma (Google AI SDK): Handles natural language understanding and generates structured intents from user queries
Backend Service (Python): Translates Gemma intents into safe Grafana/PromQL queries, executes them, and returns structured results
Grafana API & Prometheus API: Provides real-time system metrics data

Implementation Process
1. Infrastructure Setup: Configure Grafana, Windows/Node Exporter, and Prometheus. Generate required API keys for both Grafana and Gemma services.
2. Schema Creation: Build a JSON schema that validates user input metrics and maps them to proper queries. This reduces LLM hallucination and prevents incorrect responses.
3. Agent Execution: The main agent class loads the schema, initializes the Gemma model, processes user queries through prompt engineering to extract keywords, builds appropriate queries, hits the Grafana API, and returns results in natural language.

 Code Architecture

  Class: GrafanaGemmaAgent

The heart of the system is the `GrafanaGemmaAgent` class that orchestrates the entire workflow:

Initialization Process:
- Schema Loading: Reads `schema.json` to understand available metrics and their PromQL mappings
- Model Setup: Initializes Google's Gemma-2-2b-it model for natural language processing
- Configuration: Loads environment variables for API keys and Grafana endpoints


This is the main entry point that coordinates the entire flow:
```
User Input → Intent Parsing → PromQL Generation → API Execution → Natural Response
```

Purpose: Converts human language into structured data

Process:
- Sends user query with available metrics to Gemma model
- Uses carefully crafted prompts to extract:
  - Target metric (cpu_usage, memory_usage, etc.)
  - Aggregation type (avg, max, min, sum)
  - Time range (5m, 1h, 24h, etc.)
  - User intent and confidence level
- Returns structured JSON with parsed information




Purpose: Translates structured intent into executable PromQL

Process:
- Takes parsed intent (metric, aggregation, time_range)
- Retrieves base query template from schema
- Applies time range modifications (replaces [5m] with user-specified range)
- Wraps with aggregation functions (max(), min(), avg(), sum())
- Returns ready-to-execute PromQL query

Purpose: Executes PromQL against Grafana's Prometheus datasource

Process:
- Constructs Grafana API endpoint with datasource proxy
- Sends authenticated request with PromQL query
- Parses Prometheus response format
- Extracts metric values, timestamps, and labels
- Returns structured results list

5. Response Generation (`format_answer`)
Purpose: Converts raw metrics into human-readable responses

Two-stage Process:
1. Data Processing: Applies unit conversions (e.g., percentage formatting)
2. Natural Language Generation: Uses Gemma to create conversational responses

Smart Formatting: 
 Handles different units (%, MB, seconds)
 Provides context-aware descriptions
 Maintains conversational tone replace Gemma with gemma
