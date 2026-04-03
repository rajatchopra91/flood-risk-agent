import os
import json
from groq import Groq
from dotenv import load_dotenv
from tools import full_site_analysis

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """You are a flood risk analyst AI assistant for construction site evaluation in India.

You help site builders and developers understand flood risk for specific locations.

When a user asks about a location, you will receive structured analysis data and must:
1. Explain the flood risk in plain language
2. Highlight the key factors (elevation, catchment area, flow accumulation)
3. Give a clear recommendation for construction suitability
4. Mention any precautions if risk is moderate or high

Always be specific, cite the numbers, and be helpful to a non-technical audience.
Keep your response concise — 3 to 5 sentences maximum."""


def run_agent(user_query: str):
    """
    Takes a natural language query about a location,
    runs geospatial analysis, and returns an AI-generated report.
    """
    print(f"\nUser query: {user_query}")

    # Step 1: Ask Llama to extract the location from the query
    extraction = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": "Extract the location name from the user query. Return ONLY the location name, nothing else. Example: 'Koregaon Park, Pune' or 'Bandra, Mumbai'"
            },
            {
                "role": "user",
                "content": user_query
            }
        ]
    )

    location = extraction.choices[0].message.content.strip()
    print(f"Extracted location: {location}")

    # Step 2: Run geospatial analysis
    print("Running geospatial analysis...")
    try:
        analysis = full_site_analysis(location)
    except Exception as e:
        return f"Sorry, I could not analyse that location: {str(e)}"

    # Step 3: Ask Llama to generate a human-readable report
    analysis_summary = json.dumps(analysis, indent=2)

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": f"""User asked: {user_query}

Here is the geospatial analysis data:
{analysis_summary}

Please provide a clear flood risk assessment for this site."""
            }
        ]
    )

    return response.choices[0].message.content


if __name__ == "__main__":
    queries = [
        "Is Koregaon Park in Pune safe for building a residential complex?",
        "What is the flood risk for a construction site in Bandra, Mumbai?",
    ]

    for query in queries:
        print("\n" + "="*60)
        result = run_agent(query)
        print("\nAI Report:")
        print(result)
        print("="*60)