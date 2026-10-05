"""
MeetingMate AI - Backend (Flask + NLP)
======================================
A simple, explainable Python backend for meeting transcript action-item extraction
and meeting analytics. Built for college project demonstration and viva presentation.
"""

import re
import numpy as np
from flask import Flask, request, jsonify, send_from_directory

# Initialize Flask app to serve frontend files directly from current folder
app = Flask(__name__, static_folder='.', static_url_path='')

# List of common action verbs and triggers in meeting transcripts
ACTION_VERBS = [
    'complete', 'prepare', 'test', 'create', 'fix', 'send', 'review',
    'update', 'develop', 'implement', 'conduct', 'organize', 'schedule',
    'design', 'build', 'write', 'deploy', 'finish', 'submit', 'check',
    'verify', 'document', 'publish', 'research', 'present'
]

ACTION_PATTERNS = [
    r'\b(will|shall|going to|needs? to|must|should|have to|assigned to)\b',
    r'\b(action item|todo|to-do|task)\b'
]

# Common deadline patterns in conversational transcripts
DEADLINE_PATTERNS = [
    (r'\b(?:by|before|until|on)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', r'\1'),
    (r'\b(?:by|before|until)\s+(tomorrow|today|tonight|next week|end of day|eod|this weekend)\b', r'\1'),
    (r'\b(?:after|following)\s+([a-zA-Z\s]{3,20})\b', r'after \1'),
    (r'\b(?:by|on|before)\s+([a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?)\b', r'\1'),
    (r'\b(?:in\s+\d+\s+(?:days?|hours?|weeks?))\b', r'\0'),
    (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', r'\1'),
    (r'\b(tomorrow|today|next week)\b', r'\1')
]


def extract_owner(line):
    """
    Extracts the speaker or person responsible.
    If line starts with 'Rahul: ...', owner is 'Rahul'.
    If line has generic wording like 'Someone should...', owner is 'Unknown'.
    """
    # Check for Speaker: format (e.g., "Rahul: I will complete...")
    speaker_match = re.match(r'^\s*([A-Za-z0-9_\s]{2,25})\s*[:\-–]\s*(.*)$', line)
    if speaker_match:
        speaker_name = speaker_match.group(1).strip()
        sentence_body = speaker_match.group(2).strip()
        
        # Check if the speaker is talking in first person ("I will...", "I am...")
        if re.search(r'\b(i will|i\'ll|i shall|i am going to|i can|i will be)\b', sentence_body, re.I):
            return speaker_name, sentence_body
        
        # Check if speaker assigned someone else ("Aman, please finish...")
        assignee_match = re.match(r'^\s*([A-Z][a-z]+)[,\s]+(?:please|can you|you will|will you)\b', sentence_body, re.I)
        if assignee_match:
            return assignee_match.group(1).strip(), sentence_body
            
        return speaker_name, sentence_body

    # Check for "Someone should..." or passive sentences
    if re.search(r'\b(someone|somebody|anyone|team|we need someone to)\b', line, re.I):
        return "Unknown", line

    return "Unknown", line


def extract_deadline(text):
    """
    Detects time/date deadlines from text using pattern matching.
    Returns deadline string or 'Not specified'.
    """
    for pattern, group_fmt in DEADLINE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Clean and format the deadline
            deadline = match.group(0).strip()
            # Remove leading prepositions for cleaner output if desired, or keep neat
            deadline = re.sub(r'^(?:by|before|on|until)\s+', '', deadline, flags=re.I)
            return deadline.capitalize()
            
    return "Not specified"


def clean_task_description(sentence, deadline):
    """
    Cleans raw sentence into a concise, readable task description.
    """
    text = sentence
    # Remove speaker prefixes if any left
    text = re.sub(r'^\s*[A-Za-z0-9_\s]+[:\-–]\s*', '', text)
    
    # Remove introductory phrases like "I will", "Please make sure to", "Someone should"
    text = re.sub(r'^(?:i will|i\'ll|i shall|i am going to|someone should|please|we should|we need to|make sure to)\s+', '', text, flags=re.I)
    
    # Remove deadline mention and its leading preposition from task to keep task name neat
    if deadline != "Not specified":
        # Remove preposition + deadline (e.g. "by Friday", "before Monday", "after development")
        text = re.sub(rf'\b(?:by|before|on|until|after)\s+{re.escape(deadline)}\b', '', text, flags=re.I)
        # Remove deadline alone if still present
        text = re.sub(re.escape(deadline), '', text, flags=re.I)
        # Clean trailing prepositions
        text = re.sub(r'\b(by|before|on|until|after)\s*$', '', text, flags=re.I)
        
    text = text.strip(' .;,:-')
    if text:
        text = text[0].upper() + text[1:]
    return text if len(text) > 3 else sentence.strip()


def calculate_confidence(has_task_verb, has_action_pattern, has_owner, has_deadline):
    """
    Uses NumPy numerical weighting to calculate an explainable confidence score.
    College Viva explanation:
    - Base action presence (Verb / Pattern): 45%
    - Concrete Owner identified: 30%
    - Clear Deadline identified: 20%
    - Minimum baseline: 5%
    """
    weights = np.array([0.45, 0.30, 0.20, 0.05])
    features = np.array([
        1.0 if (has_task_verb or has_action_pattern) else 0.4,
        1.0 if has_owner and has_owner != "Unknown" else 0.2,
        1.0 if has_deadline and has_deadline != "Not specified" else 0.3,
        1.0
    ])
    
    # Dot product calculation using NumPy
    score = np.dot(weights, features)
    # Clip between 0.50 and 0.98 for realistic scoring
    final_score = float(np.clip(score, 0.50, 0.98))
    return round(final_score * 100, 1)


def parse_transcript(transcript_text):
    """
    Main NLP Pipeline:
    1. Splits transcript into lines.
    2. Identifies action-oriented sentences.
    3. Extracts Owner, Task, Deadline.
    4. Computes NumPy Confidence Score.
    5. Flags Needs Review items.
    """
    lines = transcript_text.strip().split('\n')
    action_items = []
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        owner, sentence_body = extract_owner(line_clean)
        
        # Check if this sentence represents an action/task
        has_verb = any(re.search(rf'\b{verb}\b', sentence_body, re.I) for verb in ACTION_VERBS)
        has_pattern = any(re.search(pat, sentence_body, re.I) for pat in ACTION_PATTERNS)
        
        # Check if line looks like an action item
        if has_verb or has_pattern or ":" in line_clean:
            deadline = extract_deadline(sentence_body)
            task = clean_task_description(sentence_body, deadline)
            
            if not task:
                continue
                
            confidence = calculate_confidence(
                has_task_verb=has_verb,
                has_action_pattern=has_pattern,
                has_owner=(owner != "Unknown"),
                has_deadline=(deadline != "Not specified")
            )
            
            # Status determination
            if owner == "Unknown" or confidence < 70.0:
                status = "Needs Review"
            else:
                status = "Pending"
                
            action_items.append({
                "task": task,
                "owner": owner,
                "deadline": deadline,
                "status": status,
                "confidence": confidence
            })
            
    # Calculate statistics using NumPy
    total_items = len(action_items)
    if total_items > 0:
        conf_scores = np.array([item["confidence"] for item in action_items])
        high_conf_count = int(np.sum(conf_scores >= 80.0))
        needs_review_count = int(np.sum([1 for item in action_items if item["status"] == "Needs Review"]))
        unique_owners = len(set(item["owner"] for item in action_items if item["owner"] != "Unknown"))
    else:
        high_conf_count = 0
        needs_review_count = 0
        unique_owners = 0
        
    return {
        "action_items": action_items,
        "summary": {
            "total_items": total_items,
            "high_confidence": high_conf_count,
            "needs_review": needs_review_count,
            "unique_owners": unique_owners
        }
    }


# ==========================================
# Flask Routes
# ==========================================

@app.route('/')
def serve_index():
    """Serves the main single-page application"""
    return send_from_directory('.', 'index.html')


@app.route('/analyze', methods=['POST'])
def analyze_meeting():
    """
    API endpoint: Accepts transcript text and returns extracted action items.
    """
    try:
        data = request.get_json(silent=True) or {}
        transcript = data.get('transcript', '')
        
        if not transcript.strip():
            return jsonify({
                "error": "Please provide transcript text to analyze.",
                "action_items": [],
                "summary": {"total_items": 0, "high_confidence": 0, "needs_review": 0, "unique_owners": 0}
            }), 400
            
        results = parse_transcript(transcript)
        return jsonify(results)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("==================================================")
    print("  🚀 MeetingMate AI Server Running on http://127.0.0.1:5000")
    print("==================================================")
    app.run(host='127.0.0.1', port=5000, debug=True)
