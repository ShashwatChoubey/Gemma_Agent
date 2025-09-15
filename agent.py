import json
import requests
import os
from dotenv import load_dotenv
import google.generativeai as genai
from typing import Dict, List, Any
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000")
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY is required in .env file")

genai.configure(api_key=GOOGLE_API_KEY)

class GrafanaGemmaAgent:
    def __init__(self, schema_file: str = "schema.json"):
        self.load_schema(schema_file)
        self.setup_gemma_model()
        self.conversation_history = []
        
    def load_schema(self, schema_file: str):
        try:
            with open(schema_file, "r") as f:
                self.schema = json.load(f)["metrics"]
            logger.info(f"Loaded {len(self.schema)} metrics from schema")
        except FileNotFoundError:
            logger.error(f"Schema file {schema_file} not found")
            raise
        except KeyError:
            logger.error("Invalid schema format - 'metrics' key not found")
            raise
    
    def setup_gemma_model(self):
        gemma_models = [
    'gemma-3-27b-it',
    'gemma-3-12b-it',
    'gemma-3-4b-it',
    'gemma-3-1b-it'
]

        
        for model_name in gemma_models:
            try:
                self.model = genai.GenerativeModel(model_name)
               
                logger.info(f"Successfully initialized {model_name}")
                break
            except Exception as e:
                logger.warning(f"Failed to initialize {model_name}: {e}")
                continue
        else:
            raise Exception("All Gemma model initialization attempts failed")
    
    def parse_user_query(self, user_query: str) -> Dict[str, Any]:
        available_metrics = list(self.schema.keys())
        metrics_info = "\n".join([
            f"- {metric}: {info['description']} (unit: {info.get('unit', 'N/A')})"
            for metric, info in self.schema.items()
        ])
        
        prompt = f"""
You are a system monitoring assistant using Gemma model. Parse the following user query into a structured JSON format.

Available metrics:
{metrics_info}

User query: "{user_query}"

Extract the following information and respond with ONLY a valid JSON object:
{{
    "metric": "exact_metric_name_from_list_above",
    "aggregation": "avg|max|min|sum",
    "time_range": "5m|15m|1h|6h|24h",
    "intent": "brief_description_of_what_user_wants",
    "confidence": 0.0-1.0
}}

Rules:
1. If no specific aggregation is mentioned, use "avg"
2. If no time range is mentioned, use "5m"
3. Match the closest metric from the available list
4. Set confidence based on how certain you are about the mapping
5. If you can't determine the metric, set it to null

Examples:
- "What's the CPU usage?" → {{"metric": "cpu_usage", "aggregation": "avg", "time_range": "5m", "intent": "get current CPU usage", "confidence": 0.9}}
- "Show me maximum memory consumption in the last hour" → {{"metric": "memory_usage", "aggregation": "max", "time_range": "1h", "intent": "get peak memory usage", "confidence": 0.95}}

Respond with ONLY the JSON object, no other text.
"""
        
        response = self.model.generate_content(prompt)
        response_text = response.text.strip()
        
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            intent = json.loads(json_str)
            
            if intent.get("metric") not in self.schema and intent.get("metric") is not None:
                intent["metric"] = self.find_closest_metric(user_query)
                intent["confidence"] = max(0.3, intent.get("confidence", 0.5) - 0.2)
            
            return intent
        else:
            raise ValueError("No valid JSON found in Gemma response")
    
    def find_closest_metric(self, user_query: str) -> str:
        prompt = f"""
Using Gemma model, analyze this user query: "{user_query}"

Available metrics:
{list(self.schema.keys())}

Which metric from the list above is most relevant to the user's question?
Respond with ONLY the metric name, nothing else.
"""
        
        response = self.model.generate_content(prompt)
        metric_name = response.text.strip().lower()
        
        if metric_name in self.schema:
            return metric_name
        
        for metric in self.schema.keys():
            if metric.lower() in response.text.lower():
                return metric
        
        return list(self.schema.keys())[0]
    
    def build_promql(self, intent: Dict[str, Any]) -> str:
        metric = intent.get("metric")
        agg = intent.get("aggregation", "avg")
        time_range = intent.get("time_range", "5m")
        
        if not metric or metric not in self.schema:
            raise ValueError(f"Metric '{metric}' not in schema")
        
        base_query = self.schema[metric]["example_query"]
        
        if "[5m]" in base_query and time_range != "5m":
            base_query = base_query.replace("[5m]", f"[{time_range}]")
        
        if agg == "max":
            return f"max({base_query})"
        elif agg == "min":
            return f"min({base_query})"
        elif agg == "sum":
            return f"sum({base_query})"
        elif agg == "avg":
            return f"avg({base_query})"
        else:
            return base_query
    
    def execute_promql(self, promql: str, datasource_id: int = 1) -> List[Dict[str, Any]]:
        if not GRAFANA_API_KEY:
            raise ValueError("Grafana API key not configured")
            
        url = f"{GRAFANA_URL}/api/datasources/proxy/{datasource_id}/api/v1/query"
        headers = {"Authorization": f"Bearer {GRAFANA_API_KEY}"}
        params = {"query": promql}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for result in data.get("data", {}).get("result", []):
                metric_labels = result.get("metric", {})
                value = result.get("value", [])
                if value:
                    timestamp, metric_value = value
                    results.append({
                        "labels": metric_labels,
                        "timestamp": timestamp,
                        "value": float(metric_value)
                    })
            
            return results
            
        except requests.RequestException as e:
            logger.error(f"Error executing PromQL query: {e}")
            raise
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing Grafana response: {e}")
            raise
    
    def format_answer(self, intent: Dict[str, Any], metrics: List[Dict[str, Any]]) -> str:
        if not metrics:
            return "No data found for this metric and time range."
        
        metric_name = intent["metric"]
        metric_info = self.schema[metric_name]
        value = metrics[0]["value"]
        unit = metric_info.get("unit", "")
        
        if unit == "%":
            value *= 100
        
        agg = intent.get("aggregation", "avg").capitalize()
        formatted_value = f"{value:.2f}{unit}"
        
        prompt = f"""
You are using Gemma model to generate a natural, conversational response for a system monitoring query.

User asked: "{intent['intent']}"
Metric: {metric_info['description']}
Aggregation: {agg}
Value: {formatted_value}
Time range: {intent.get('time_range', '5m')}

Generate a brief, helpful response (1-2 sentences) that:
1. Directly answers the user's question
2. Provides the specific value with appropriate context
3. Uses natural language (avoid technical jargon)

Example: "The current average CPU usage is 15.6%, which indicates normal system load."

Respond with only the natural language answer, no other text.
"""
        
        response = self.model.generate_content(prompt)
        return response.text.strip()
    
    def process_query(self, user_query: str, datasource_id: int = 1) -> str:
        try:
            logger.info(f"Processing query with Gemma: {user_query}")
            
            intent = self.parse_user_query(user_query)
            logger.info(f"Gemma parsed intent: {intent}")
            
            if not intent.get("metric"):
                return "I couldn't understand which metric you're asking about. Please try asking about CPU usage, memory usage, GPU utilization, or system uptime."
            
            promql = self.build_promql(intent)
            logger.info(f"Generated PromQL: {promql}")
            
            metrics = self.execute_promql(promql, datasource_id)
            logger.info(f"Query returned {len(metrics)} results")
            
            answer = self.format_answer(intent, metrics)
            
            self.conversation_history.append({
                "query": user_query,
                "intent": intent,
                "promql": promql,
                "results": metrics,
                "answer": answer,
                "model_used": "gemma"
            })
            
            return answer
            
        except Exception as e:
            logger.error(f"Error processing query with Gemma: {e}")
            return f"I encountered an error while processing your query: {str(e)}"
    
    def get_available_metrics(self) -> str:
        metrics_list = []
        for metric, info in self.schema.items():
            metrics_list.append(f"• {info['description']} ({metric})")
        
        return "Available metrics (powered by Gemma):\n" + "\n".join(metrics_list)

def main():
    try:
        print("Initializing Grafana Agent with Gemma model...")
        agent = GrafanaGemmaAgent()
        
        test_queries = [
            "What's the current CPU usage?",
            "Show me maximum memory usage in the last hour",
            "How long has the system been running?",
            "What's the GPU utilization?",
            "Give me the average CPU usage"
        ]
        
        print(agent.get_available_metrics())
        print("\n" + "="*50 + "\n")
        
        for i, query in enumerate(test_queries, 1):
            print(f"Query {i}: {query}")
            answer = agent.process_query(query)
            print(f"Gemma Answer: {answer}")
            print("-" * 30)
        
        print("\nEntering interactive mode. Type 'quit' to exit.")
        print("All responses are powered by Gemma model via Google AI SDK.")
        while True:
            user_input = input("\nYour question: ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            
            if not user_input:
                continue
                
            answer = agent.process_query(user_input)
            print(f"Gemma: {answer}")
    
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        print(f"Failed to initialize Gemma agent: {e}")
        print("\nPlease ensure:")
        print("1. schema.json file exists and is properly formatted")
        print("2. GRAFANA_URL and GRAFANA_API_KEY are set in .env file")
        print("3. GOOGLE_API_KEY is set in .env file for Gemma model access")
        print("4. You have access to Gemma models through Google AI SDK")

if __name__ == "__main__":
    main()