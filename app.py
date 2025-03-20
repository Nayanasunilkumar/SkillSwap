from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_cors import CORS
import hashlib
import json
import os
from functools import wraps
from werkzeug.utils import secure_filename
from datetime import datetime
import time

app = Flask(__name__)
CORS(app)
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key

# Ensure the data directory exists
if not os.path.exists('data'):
    os.makedirs('data')

# Initialize JSON files if they don't exist
def init_json_files():
    files = ['users.json', 'skills.json', 'user_skills.json', 'user_interests.json', 'connections.json']
    for file in files:
        path = f'data/{file}'
        if not os.path.exists(path):
            with open(path, 'w') as f:
                if file == 'skills.json':
                    json.dump({}, f)
                elif file == 'connections.json':
                    json.dump([], f)
                else:
                    json.dump([], f)

init_json_files()

def load_json(filename):
    try:
        with open(f'data/{filename}', 'r') as f:
            return json.load(f)
    except:
        return [] if filename != 'skills.json' else {}

def save_json(data, filename):
    with open(f'data/{filename}', 'w') as f:
        json.dump(data, f, indent=4)

def hash_password(password):
    salt = "skillswap_salt"
    salted_password = password + salt
    return hashlib.sha256(salted_password.encode()).hexdigest()

def verify_password(stored_hash, password):
    salt = "skillswap_salt"
    salted_password = password + salt
    return stored_hash == hashlib.sha256(salted_password.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Configure upload folder
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'profiles')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.context_processor
def inject_profile():
    if 'user_id' in session:
        user_id = str(session['user_id'])
        profiles = load_json('profile.json')
        user_profiles = [p for p in profiles['profiles'] if str(p['user_id']) == user_id]
        user_profile = max(user_profiles, key=lambda x: x.get('updated_at', '')) if user_profiles else None
        
        if not user_profile:
            user_profile = {
                "user_id": user_id,
                "profile_picture": "default-avatar.png",
                "about": "",
                "location": "",
                "interests": [],
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            profiles['profiles'].append(user_profile)
            save_json(profiles, 'profile.json')
        
        return {'profile': user_profile}
    return {'profile': None}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        users = load_json('users.json')
        user = next((user for user in users if user['email'] == email), None)
        
        if user and verify_password(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['fullname']
            flash('Successfully logged in!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))
        
        users = load_json('users.json')
        
        if any(user['email'] == email for user in users):
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        new_user = {
            'id': len(users) + 1,
            'fullname': fullname,
            'email': email,
            'password': hash_password(password),
            'about': ''
        }
        
        users.append(new_user)
        save_json(users, 'users.json')
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = str(session['user_id'])
    
    # Load profile data
    profiles = load_json('profile.json')
    users = load_json('users.json')
    user_profile = next((p for p in profiles['profiles'] if str(p['user_id']) == user_id), None)
    
    # Load skills data
    skills_data = load_json('skills.json')
    user_skills = skills_data.get('user_skills', {}).get(user_id, [])
    
    # Get user's interests
    user_interests = user_profile.get('interests', []) if user_profile else []
    
    # Get other users' skills
    other_users_skills = []
    for profile in profiles['profiles']:
        if str(profile['user_id']) != user_id:
            user_data = next((u for u in users if str(u['id']) == str(profile['user_id'])), None)
            user_skills_list = skills_data.get('user_skills', {}).get(str(profile['user_id']), [])
            if user_skills_list and user_data:
                for skill in user_skills_list:
                    other_users_skills.append({
                        'user_id': str(user_data['id']),  # Ensure user_id is a string
                        'user_name': user_data['fullname'],
                        'profile_picture': profile.get('profile_picture', 'default-avatar.png'),
                        'skill_name': skill['skill_name'],
                        'qualification': skill['qualification'],
                        'years_of_experience': skill['years_of_experience'],
                        'description': skill['description'],
                        'matches_interest': skill['skill_name'] in user_interests
                    })
    
    # Sort skills: prioritize matching interests, then by years of experience
    other_users_skills.sort(key=lambda x: (-x['matches_interest'], -x['years_of_experience']))
    
    # Get featured users (users with similar interests)
    featured_users = []
    for profile in profiles['profiles']:
        if str(profile['user_id']) != user_id:
            user_data = next((u for u in users if str(u['id']) == str(profile['user_id'])), None)
            user_skills_list = skills_data.get('user_skills', {}).get(str(profile['user_id']), [])
            if user_skills_list and user_data:
                featured_users.append({
                    'id': str(user_data['id']),
                    'name': user_data['fullname'],
                    'profile_picture': profile.get('profile_picture', 'default-avatar.png'),
                    'skills': [skill['skill_name'] for skill in user_skills_list[:3]]
                })
    
    return render_template('dashboard.html',
                         active_page='home',
                         profile=user_profile,
                         user_skills=user_skills,
                         other_users_skills=other_users_skills,
                         featured_users=featured_users[:4])

@app.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    users = load_json('users.json')
    user = next((u for u in users if u['id'] == user_id), None)
    
    # Load profile data
    profiles = load_json('profile.json')
    profile_data = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    # Load user's skills from skills.json
    skills_data = load_json('skills.json')
    user_skills = skills_data.get('user_skills', {}).get(str(user_id), [])
    
    if not profile_data:
        # Create default profile if none exists
        profile_data = {
            "user_id": user_id,
            "profile_picture": "default-avatar.png",
            "about": "",
            "location": "",
            "interests": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        profiles['profiles'].append(profile_data)
        save_json(profiles, 'profile.json')
    
    return render_template('profile.html',
                         active_page='profile',
                         user=user,
                         profile=profile_data,
                         user_skills=user_skills)

@app.route('/api/profile/update', methods=['POST'])
@login_required
def update_profile():
    user_id = session['user_id']
    profiles = load_json('profile.json')
    profile_data = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    if not profile_data:
        return jsonify({'success': False, 'error': 'Profile not found'})
    
    # Handle profile picture upload
    if 'profile_picture' in request.files:
        file = request.files['profile_picture']
        if file and allowed_file(file.filename):
            try:
                filename = secure_filename(file.filename)
                # Add timestamp to filename to prevent overwriting
                filename = f"{int(time.time())}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                # Delete old profile picture if it exists and is not the default
                old_picture = profile_data.get('profile_picture')
                if old_picture and old_picture != 'default-avatar.png':
                    old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], old_picture)
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                
                # Update profile picture in profile data
                profile_data['profile_picture'] = filename
                profile_data['updated_at'] = datetime.now().isoformat()
                save_json(profiles, 'profile.json')
                return jsonify({'success': True})
            except Exception as e:
                print(f"Error uploading file: {str(e)}")
                return jsonify({'success': False, 'error': str(e)})
    
    # Handle other profile updates
    data = request.form
    profile_data['about'] = data.get('about', profile_data.get('about', ''))
    profile_data['location'] = data.get('location', profile_data.get('location', ''))
    profile_data['updated_at'] = datetime.now().isoformat()
    save_json(profiles, 'profile.json')
    
    return jsonify({'success': True})

@app.route('/api/skills/add', methods=['POST'])
@login_required
def add_skill():
    user_id = str(session['user_id'])
    data = request.get_json()
    
    if not data.get('skill_name'):
        return jsonify({'success': False, 'error': 'Skill name is required'})
    
    skills_data = load_json('skills.json')
    
    # Initialize user's skills array if it doesn't exist
    if 'user_skills' not in skills_data:
        skills_data['user_skills'] = {}
    if user_id not in skills_data['user_skills']:
        skills_data['user_skills'][user_id] = []
    
    # Create new skill with detailed information
    new_skill = {
        "skill_id": f"{data['skill_name'].lower()}_{len(skills_data['user_skills'][user_id]) + 1}",
        "skill_name": data['skill_name'],
        "description": data.get('description', ''),
        "qualification": data.get('qualification', 'Beginner'),
        "years_of_experience": data.get('years_of_experience', 0),
        "certifications": data.get('certifications', []),
        "projects": data.get('projects', []),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    
    # Add the new skill to user's skills
    skills_data['user_skills'][user_id].append(new_skill)
    save_json(skills_data, 'skills.json')
    
    return jsonify({'success': True, 'skill': new_skill})

@app.route('/api/interests/add', methods=['POST'])
@login_required
def add_user_interest():
    user_id = session['user_id']
    interest = request.get_json().get('interest')
    
    if not interest:
        return jsonify({'success': False, 'error': 'No interest provided'})
    
    user_interests = load_json('user_interests.json')
    
    interest_entry = next((item for item in user_interests if item['user_id'] == user_id), None)
    if interest_entry:
        if interest not in interest_entry['interests']:
            interest_entry['interests'].append(interest)
    else:
        user_interests.append({
            'user_id': user_id,
            'interests': [interest]
        })
    
    save_json(user_interests, 'user_interests.json')
    return jsonify({'success': True})

@app.route('/search')
@login_required
def search():
    return render_template('search.html', active_page='search')

@app.route('/api/search')
@login_required
def api_search():
    query = request.args.get('q', '').strip().lower()
    
    if not query:
        return jsonify({
            'users': [],
            'skills': []
        })
    
    results = {
        'users': [],
        'skills': []
    }
    
    # Load all necessary data
    users = load_json('users.json')
    profiles = load_json('profile.json')
    skills_data = load_json('skills.json')
    
    # Search users
    for user in users:
        if (query in user['fullname'].lower() or 
            (user.get('location') and query in user['location'].lower())):
            # Don't include the current user in results
            if str(user['id']) != str(session['user_id']):
                # Get user's profile
                user_profile = next((p for p in profiles['profiles'] if str(p['user_id']) == str(user['id'])), None)
                
                # Get user's skills
                user_skills = skills_data.get('user_skills', {}).get(str(user['id']), [])
                
                results['users'].append({
                    'id': user['id'],
                    'username': user['fullname'],
                    'location': user_profile.get('location', 'Not specified') if user_profile else 'Not specified',
                    'profile_picture': user_profile.get('profile_picture', 'default-avatar.png') if user_profile else 'default-avatar.png',
                    'about': user_profile.get('about', '') if user_profile else '',
                    'skills': [{
                        'name': skill['skill_name'],
                        'qualification': skill['qualification'],
                        'years': skill['years_of_experience']
                    } for skill in user_skills[:3]],  # Show top 3 skills
                    'total_skills': len(user_skills)
                })
    
    # Search skills
    for user_id, user_skills in skills_data.get('user_skills', {}).items():
        for skill in user_skills:
            if (query in skill['skill_name'].lower() or 
                query in skill['description'].lower()):
                # Get user information
                user = next((u for u in users if str(u['id']) == str(user_id)), None)
                if user and str(user['id']) != str(session['user_id']):
                    # Get user's profile
                    user_profile = next((p for p in profiles['profiles'] if str(p['user_id']) == str(user_id)), None)
                    
                    results['skills'].append({
                        'id': skill['skill_id'],
                        'skill_name': skill['skill_name'],
                        'description': skill['description'],
                        'qualification': skill['qualification'],
                        'years_of_experience': skill['years_of_experience'],
                        'certifications': skill.get('certifications', []),
                        'projects': skill.get('projects', []),
                        'user': {
                            'id': user['id'],
                            'username': user['fullname'],
                            'location': user_profile.get('location', 'Not specified') if user_profile else 'Not specified',
                            'profile_picture': user_profile.get('profile_picture', 'default-avatar.png') if user_profile else 'default-avatar.png',
                            'about': user_profile.get('about', '') if user_profile else ''
                        }
                    })
    
    return jsonify(results)

@app.route('/logout')
def logout():
    session.clear()
    flash('Successfully logged out', 'success')
    return redirect(url_for('login'))

@app.route('/skills')
@login_required
def skills():
    user_id = session['user_id']
    user_skills = load_json('user_skills.json')
    all_skills = load_json('skills.json')
    
    # Get current user's skills
    current_user_skills = next((item['skills'] for item in user_skills if item['user_id'] == user_id), [])
    
    # Get available skills (skills not in user's current list)
    available_skills = [
        {'name': skill, 'icon': info.get('icon', 'star'), 'description': info.get('description', '')}
        for skill, info in all_skills.items()
        if skill not in current_user_skills
    ]
    
    return render_template('skills.html',
                         active_page='skills',
                         user_skills=current_user_skills,
                         available_skills=available_skills)

@app.route('/api/skills/remove/<skill_id>', methods=['POST'])
@login_required
def remove_skill(skill_id):
    user_id = str(session['user_id'])
    skills_data = load_json('skills.json')
    
    if 'user_skills' not in skills_data or user_id not in skills_data['user_skills']:
        return jsonify({'success': False, 'error': 'No skills found'})
    
    # Remove the skill from user's skills
    skills_data['user_skills'][user_id] = [
        skill for skill in skills_data['user_skills'][user_id]
        if skill['skill_id'] != skill_id
    ]
    
    save_json(skills_data, 'skills.json')
    return jsonify({'success': True})

@app.route('/connections')
@login_required
def connections():
    user_id = session['user_id']
    users = load_json('users.json')
    user_skills = load_json('user_skills.json')
    
    # Get current user's skills
    current_user_skills = next((item['skills'] for item in user_skills if item['user_id'] == user_id), [])
    
    # Get connected users (users with matching skills)
    connected_users = []
    for user in users:
        if user['id'] == user_id:  # Skip current user
            continue
            
        user_skill_list = next((item['skills'] for item in user_skills if item['user_id'] == user['id']), [])
        
        # Check for matching skills
        matching_skills = set(current_user_skills) & set(user_skill_list)
        if matching_skills:
            connected_users.append({
                'username': user['fullname'],
                'profile_picture': url_for('static', filename='images/default-avatar.png'),
                'matching_skills': list(matching_skills)
            })
    
    return render_template('connections.html',
                         active_page='connections',
                         connected_users=connected_users)

@app.route('/api/profile/interests/add', methods=['POST'])
@login_required
def add_interest():
    user_id = session['user_id']
    interest = request.get_json().get('interest')
    
    if not interest:
        return jsonify({'success': False, 'error': 'No interest provided'})
    
    profiles = load_json('profile.json')
    profile_data = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    if profile_data and interest not in profile_data['interests']:
        profile_data['interests'].append(interest)
        profile_data['updated_at'] = datetime.now().isoformat()
        save_json(profiles, 'profile.json')
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Interest already exists'})

@app.route('/api/profile/interests/remove', methods=['POST'])
@login_required
def remove_interest():
    user_id = session['user_id']
    interest = request.get_json().get('interest')
    
    if not interest:
        return jsonify({'success': False, 'error': 'No interest provided'})
    
    profiles = load_json('profile.json')
    profile_data = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    if profile_data and interest in profile_data['interests']:
        profile_data['interests'].remove(interest)
        profile_data['updated_at'] = datetime.now().isoformat()
        save_json(profiles, 'profile.json')
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Interest not found'})

@app.route('/api/profile/education/add', methods=['POST'])
@login_required
def add_education():
    user_id = session['user_id']
    education_data = request.get_json()
    
    # Load current profile data
    profiles = load_json('profile.json')
    
    # Find user's profile
    user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    if not user_profile:
        return jsonify({'success': False, 'message': 'Profile not found'})
    
    # Initialize education list if it doesn't exist
    if 'education' not in user_profile:
        user_profile['education'] = []
    
    # Add new education entry
    user_profile['education'].append(education_data)
    user_profile['updated_at'] = datetime.now().isoformat()
    
    # Save updated profile data
    save_json(profiles, 'profile.json')
    
    return jsonify({'success': True})

@app.route('/api/profile/work/add', methods=['POST'])
@login_required
def add_work():
    user_id = session['user_id']
    work_data = request.get_json()
    
    # Load current profile data
    profiles = load_json('profile.json')
    
    # Find user's profile
    user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
    
    if not user_profile:
        return jsonify({'success': False, 'message': 'Profile not found'})
    
    # Initialize work experience list if it doesn't exist
    if 'work_experience' not in user_profile:
        user_profile['work_experience'] = []
    
    # Add new work experience entry
    user_profile['work_experience'].append(work_data)
    user_profile['updated_at'] = datetime.now().isoformat()
    
    # Save updated profile data
    save_json(profiles, 'profile.json')
    
    return jsonify({'success': True})

@app.route('/api/profile/education/<education_id>', methods=['GET'])
@login_required
def get_education(education_id):
    try:
        user_id = session['user_id']
        profiles = load_json('profile.json')
        
        # Find user's profile
        user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
        
        if not user_profile or 'education' not in user_profile:
            return jsonify({'success': False, 'message': 'Profile or education not found'})
        
        education = next((edu for edu in user_profile['education'] if edu['id'] == education_id), None)
        
        if not education:
            return jsonify({'success': False, 'message': 'Education not found'})
        
        return jsonify({'success': True, 'education': education})
    except Exception as e:
        print(f"Error in get_education: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/profile/education/update', methods=['POST'])
@login_required
def update_education():
    try:
        user_id = session['user_id']
        education_data = request.get_json()
        
        profiles = load_json('profile.json')
        user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
        
        if not user_profile or 'education' not in user_profile:
            return jsonify({'success': False, 'message': 'Profile or education not found'})
        
        education_list = user_profile['education']
        
        # Find and update the education entry
        for i, edu in enumerate(education_list):
            if edu['id'] == education_data['id']:
                education_list[i] = education_data
                break
        
        user_profile['education'] = education_list
        user_profile['updated_at'] = datetime.now().isoformat()
        
        save_json(profiles, 'profile.json')
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in update_education: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/profile/work/<work_id>', methods=['GET'])
@login_required
def get_work(work_id):
    try:
        user_id = session['user_id']
        profiles = load_json('profile.json')
        
        # Find user's profile
        user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
        
        if not user_profile or 'work_experience' not in user_profile:
            return jsonify({'success': False, 'message': 'Profile or work experience not found'})
        
        work = next((w for w in user_profile['work_experience'] if w['id'] == work_id), None)
        
        if not work:
            return jsonify({'success': False, 'message': 'Work experience not found'})
        
        return jsonify({'success': True, 'work': work})
    except Exception as e:
        print(f"Error in get_work: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/profile/work/update', methods=['POST'])
@login_required
def update_work():
    try:
        user_id = session['user_id']
        work_data = request.get_json()
        
        profiles = load_json('profile.json')
        user_profile = next((p for p in profiles['profiles'] if p['user_id'] == user_id), None)
        
        if not user_profile or 'work_experience' not in user_profile:
            return jsonify({'success': False, 'message': 'Profile or work experience not found'})
        
        work_list = user_profile['work_experience']
        
        # Find and update the work entry
        for i, work in enumerate(work_list):
            if work['id'] == work_data['id']:
                work_list[i] = work_data
                break
        
        user_profile['work_experience'] = work_list
        user_profile['updated_at'] = datetime.now().isoformat()
        
        save_json(profiles, 'profile.json')
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in update_work: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/skills/<skill_id>', methods=['GET'])
@login_required
def get_skill(skill_id):
    try:
        user_id = str(session['user_id'])
        skills_data = load_json('skills.json')
        
        if 'user_skills' not in skills_data or user_id not in skills_data['user_skills']:
            return jsonify({'success': False, 'message': 'No skills found'})
        
        skill = next((s for s in skills_data['user_skills'][user_id] if s['skill_id'] == skill_id), None)
        
        if not skill:
            return jsonify({'success': False, 'message': 'Skill not found'})
        
        return jsonify({'success': True, 'skill': skill})
    except Exception as e:
        print(f"Error in get_skill: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/skills/update', methods=['POST'])
@login_required
def update_skill():
    try:
        user_id = str(session['user_id'])
        skill_data = request.get_json()
        
        if not skill_data.get('skill_id'):
            return jsonify({'success': False, 'message': 'Skill ID is required'})
        
        skills_data = load_json('skills.json')
        
        if 'user_skills' not in skills_data or user_id not in skills_data['user_skills']:
            return jsonify({'success': False, 'message': 'No skills found'})
        
        skill_list = skills_data['user_skills'][user_id]
        
        # Find and update the skill
        for i, skill in enumerate(skill_list):
            if skill['skill_id'] == skill_data['skill_id']:
                skill_list[i] = {
                    **skill,
                    **skill_data,
                    'updated_at': datetime.now().isoformat()
                }
                break
        
        skills_data['user_skills'][user_id] = skill_list
        save_json(skills_data, 'skills.json')
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error in update_skill: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'})

@app.route('/api/profile/<user_id>')
def get_user_profile(user_id):
    try:
        # Load user data from JSON files
        users = load_json('users.json')
        profiles = load_json('profile.json')
        skills_data = load_json('skills.json')
        
        # Find user
        user = next((u for u in users if str(u['id']) == str(user_id)), None)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get user's profile
        user_profile = next((p for p in profiles['profiles'] if str(p['user_id']) == str(user_id)), None)
        
        # Get user's skills
        user_skills = skills_data.get('user_skills', {}).get(str(user_id), [])
        
        # Prepare response
        response = {
            'id': user['id'],
            'name': user['fullname'],
            'email': user['email'],
            'location': user_profile.get('location', 'Not specified') if user_profile else 'Not specified',
            'profile_picture': user_profile.get('profile_picture', 'default-avatar.png') if user_profile else 'default-avatar.png',
            'skills': user_skills
        }
        
        return jsonify(response)
    except Exception as e:
        print(f"Error fetching user profile: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/connections', methods=['GET'])
@login_required
def get_connections():
    """Get all connections for the current user"""
    try:
        connections = load_json('connections.json')
        current_user_id = session['user_id']
        users = load_json('users.json')
        profiles = load_json('profile.json')
        skills_data = load_json('skills.json')

        print(f"Current user ID: {current_user_id}")
        print(f"All connections: {connections}")
        print(f"All users: {users}")

        # Filter connections for current user
        pending_connections = []
        connected_users = []

        for conn in connections:
            print(f"Processing connection: {conn}")
            # Check if this connection involves the current user
            if str(conn['user_id']) != str(current_user_id) and str(conn['connected_user_id']) != str(current_user_id):
                print(f"Skipping connection - not relevant to current user")
                continue

            # Get user information based on who initiated the connection
            if str(conn['user_id']) == str(current_user_id):
                other_user_id = conn['connected_user_id']
                print(f"Current user is sender, other user ID: {other_user_id}")
            else:
                other_user_id = conn['user_id']
                print(f"Current user is receiver, other user ID: {other_user_id}")

            # Get user details
            user = next((u for u in users if str(u['id']) == str(other_user_id)), None)
            if not user:
                print(f"User not found for ID: {other_user_id}")
                continue

            # Get user profile
            user_profile = next((p for p in profiles['profiles'] if str(p['user_id']) == str(other_user_id)), None)
            
            # Get user skills
            user_skills = skills_data.get('user_skills', {}).get(str(other_user_id), [])
            matching_skills = [skill['skill_name'] for skill in user_skills]

            # Prepare user data
            user_data = {
                'id': user['id'],
                'username': user['fullname'],
                'profile_picture': user_profile.get('profile_picture', 'default-avatar.png') if user_profile else 'default-avatar.png',
                'matching_skills': matching_skills
            }

            if conn['status'] == 'pending':
                print(f"Adding pending connection: {conn}")
                # Include the original connection data for proper status display
                pending_connections.append({
                    'id': conn['id'],
                    'user': user_data,
                    'user_id': conn['user_id'],  # Include who sent the request
                    'connected_user_id': conn['connected_user_id'],
                    'created_at': conn['created_at']
                })
            elif conn['status'] == 'connected':
                print(f"Adding connected user: {user_data}")
                connected_users.append(user_data)

        print(f"Final pending connections: {pending_connections}")
        print(f"Final connected users: {connected_users}")

        return jsonify({
            'pending_connections': pending_connections,
            'connected_users': connected_users
        })
    except Exception as e:
        print(f"Error in get_connections: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/connections/accept/<connection_id>', methods=['POST'])
@login_required
def accept_connection(connection_id):
    """Accept a connection request"""
    try:
        connections = load_json('connections.json')
        current_user_id = str(session['user_id'])  # Convert to string for comparison
        
        print(f"Accepting connection {connection_id} for user {current_user_id}")
        print(f"All connections: {connections}")
        
        # Find the connection
        connection = next((conn for conn in connections if str(conn['id']) == str(connection_id)), None)
        if not connection:
            print(f"Connection {connection_id} not found")
            return jsonify({'success': False, 'message': 'Connection not found'}), 404
            
        print(f"Found connection: {connection}")
        print(f"Connection receiver ID: {connection['connected_user_id']}")
        print(f"Current user ID: {current_user_id}")
            
        # Verify the current user is the receiver of the request
        if str(connection['connected_user_id']) != current_user_id:
            print(f"Unauthorized access attempt. Current user: {current_user_id}, Connection receiver: {connection['connected_user_id']}")
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
            
        # Update connection status
        connection['status'] = 'connected'
        connection['accepted_at'] = datetime.now().isoformat()
        
        # Save updated connections
        save_json(connections, 'connections.json')
        print("Connection updated successfully")
        
        return jsonify({'success': True, 'message': 'Connection request accepted'})
    except Exception as e:
        print(f"Error in accept_connection: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/connections/reject/<connection_id>', methods=['POST'])
@login_required
def reject_connection(connection_id):
    """Reject a connection request"""
    try:
        connections = load_json('connections.json')
        current_user_id = session['user_id']

        # Find the connection
        connection = next((conn for conn in connections if conn['id'] == connection_id), None)
        
        if not connection:
            return jsonify({'success': False, 'message': 'Connection not found'}), 404

        # Verify the current user is the recipient
        if connection['connected_user_id'] != current_user_id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403

        # Remove the connection
        connections = [conn for conn in connections if conn['id'] != connection_id]
        save_json(connections, 'connections.json')

        return jsonify({'success': True, 'message': 'Connection rejected'})
    except Exception as e:
        print(f"Error in reject_connection: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/connections/request', methods=['POST'])
@login_required
def request_connection():
    """Send a connection request"""
    try:
        data = request.get_json()
        target_user_id = data.get('user_id')
        
        if not target_user_id:
            return jsonify({'success': False, 'message': 'Target user ID is required'}), 400

        connections = load_json('connections.json')
        current_user_id = session['user_id']

        # Check if connection already exists
        existing_connection = next(
            (conn for conn in connections 
             if (conn['user_id'] == current_user_id and conn['connected_user_id'] == target_user_id) or
             (conn['user_id'] == target_user_id and conn['connected_user_id'] == current_user_id)),
            None
        )

        if existing_connection:
            return jsonify({'success': False, 'message': 'Connection already exists'}), 400

        # Create new connection request
        new_connection = {
            'id': str(len(connections) + 1),
            'user_id': current_user_id,
            'connected_user_id': target_user_id,
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }

        connections.append(new_connection)
        save_json(connections, 'connections.json')

        return jsonify({'success': True, 'message': 'Connection request sent'})
    except Exception as e:
        print(f"Error in request_connection: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/connections/test', methods=['POST'])
@login_required
def test_connection():
    """Create a test connection request"""
    try:
        connections = load_json('connections.json')
        current_user_id = str(session['user_id'])
        
        # Create a test connection request
        test_connection = {
            'id': str(len(connections) + 1),
            'user_id': current_user_id,  # Current user sends the request
            'connected_user_id': '2',  # Connect to user with ID 2 (as string)
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }

        connections.append(test_connection)
        save_json(connections, 'connections.json')

        return jsonify({'success': True, 'message': 'Test connection request created'})
    except Exception as e:
        print(f"Error in test_connection: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/api/connections/debug', methods=['GET'])
@login_required
def debug_connections():
    """Debug route to check connection data structure"""
    try:
        connections = load_json('connections.json')
        current_user_id = str(session['user_id'])
        
        # Convert all IDs to strings for consistent comparison
        debug_connections = []
        for conn in connections:
            debug_conn = {
                'id': str(conn['id']),
                'user_id': str(conn['user_id']),
                'connected_user_id': str(conn['connected_user_id']),
                'status': conn['status'],
                'created_at': conn['created_at']
            }
            debug_connections.append(debug_conn)
        
        return jsonify({
            'current_user_id': current_user_id,
            'current_user_id_type': str(type(current_user_id)),
            'connections': debug_connections
        })
    except Exception as e:
        print(f"Error in debug_connections: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(debug=True)