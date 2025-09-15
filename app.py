from flask import Flask, render_template_string, request, jsonify
import logging
from agent import GrafanaGemmaAgent 


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


agent = None

def initialize_agent():
    global agent
    try:
        agent = GrafanaGemmaAgent()
        logger.info("Agent initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        return False

@app.route('/')
def index():
    """Serve the simple query interface"""
    with open('templates/index.html', 'r') as f:
        html_content = f.read()
    return render_template_string(html_content)

@app.route('/api/query', methods=['POST'])
def handle_query():
    """Handle user queries"""
    try:
        data = request.get_json()
        user_query = data.get('query', '').strip()
        
        if not user_query:
            return jsonify({'error': 'No query provided'}), 400
        
        if not agent:
            return jsonify({'error': 'Agent not initialized'}), 500
        
        # Process query using your existing agent
        answer = agent.process_query(user_query)
        
        return jsonify({
            'query': user_query,
            'answer': answer
        })
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/health')
def health_check():
    """Simple health check"""
    return jsonify({
        'status': 'healthy',
        'agent_ready': agent is not None
    })

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f'Server Error: {error}')
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Initialize the agent
    if not initialize_agent():
        print("Warning: Agent initialization failed")
    
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)