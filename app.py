from flask import Flask, request, jsonify, send_from_directory, send_file, render_template, redirect, url_for, session, flash, current_app
from flask_cors import CORS
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy # 导入 SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash # 用于密码哈希
from rdkit import Chem
from rdkit.Chem import AllChem, Draw, Descriptors, rdMolDescriptors
from datetime import datetime, timedelta
from PIL import Image
import io
import json
import base64
from chat_storage import ChatSessionStorage
import os
import logging
from typing import Dict, Any, Union, List
import traceback # 用于在 simulate 路由中进行更详细的错误记录

# --- Email Verification Imports ---
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer

from simulate_ai import (
    get_chemistry_lab,
    process_smiles,
    process_smiles_for_3d,
    llava_call,
    llava_config_list,
    tavily_search,
    process_search_results,
    is_valid_url,
    MoleculeValidator
)
import random
import time
# from concurrent.futures import ThreadPoolExecutor # 如果未使用，可以注释掉
# from browser_automation import execute_chemical_purchase # 如果未使用，可以注释掉

# 配置日志记录
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- SQLAlchemy 设置 ---
db = SQLAlchemy()
# --- Flask-Mail Setup ---
mail = Mail()

class User(db.Model): # 定义用户模型
    __tablename__ = 'users' # 定义表名
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False) # Email is now mandatory
    password_hash = db.Column(db.String(256), nullable=False) # 增加密码哈希长度
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    email_verification_token = db.Column(db.String(120), unique=True, nullable=True)

    def get_email_verification_token(self, expires_sec=1800): # Token expires in 30 minutes (1800 seconds)
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps(self.email, salt='email-confirm-salt') # Use a salt for security

    @staticmethod
    def verify_email_token(token, expires_sec=1800):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            email = s.loads(
                token,
                salt='email-confirm-salt',
                max_age=expires_sec
            )
        except Exception as e: # Catches SignatureExpired, BadTimeSignature, etc.
            logger.warning(f"Email token verification failed: {e}")
            return None
        return email

    def __repr__(self):
        return f'<User {self.username}>'

chat_storage = ChatSessionStorage()

def create_app():
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_very_secret_and_complex_key_here_CHANGE_ME_AGAIN_AND_AGAIN')
    
    # --- 数据库配置 ---
    instance_path = os.path.join(app.instance_path)
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)
        logger.info(f"Instance path created at {instance_path}")

    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(instance_path, 'chemistry_lab.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False 

    # --- Flask-Mail Configuration for Alibaba Cloud DirectMail ---
    # IMPORTANT: Use environment variables for sensitive data in production!
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtpdm.aliyun.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 465)) # 465 for SSL, 80 or 25 for non-SSL/TLS
    app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'True').lower() == 'true'
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'False').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME') # Your DirectMail username (e.g., noreply@yourdomain.com)
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD') # Your DirectMail password or app-specific password
    app.config['MAIL_DEFAULT_SENDER'] = (
        os.environ.get('MAIL_SENDER_NAME', 'GVIM Chemistry Assistant'), # Sender Name
        os.environ.get('MAIL_SENDER_EMAIL', 'noreply@yourdomain.com') # Sender Email (verified in DirectMail)
    )
    # Check if essential mail configurations are set
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD'] or not app.config['MAIL_DEFAULT_SENDER'][1] == 'noreply@yourdomain.com':
        logger.warning("MAIL_USERNAME, MAIL_PASSWORD, or MAIL_SENDER_EMAIL not configured. Email sending will likely fail.")
        logger.warning("Please set these environment variables for email functionality.")


    db.init_app(app) 
    mail.init_app(app) # Initialize Flask-Mail

    with app.app_context(): 
        try:
            db.create_all() 
            logger.info("Database tables checked/created.")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")

    CORS(app)

    try:
        from browser_setup import setup_browser_use
        browser_use_available = setup_browser_use()
        logger.info(f"Browser-use initialization {'successful' if browser_use_available else 'failed'}")
    except ImportError:
        browser_use_available = False
        logger.warning("browser_setup module not found, browser-use functionality will be unavailable.")
    except Exception as e:
        browser_use_available = False
        logger.error(f"Error initializing browser-use: {str(e)}")

    os.makedirs(os.path.join(app.static_folder, "screenshots"), exist_ok=True)

    chemistry_lab = None
    literature_path_nonlocal = {"path": ""} 
    web_url_path_nonlocal = {"path": ""}    
    molecule_validator = MoleculeValidator()

    # --- Authentication Routes (Using SQLAlchemy) ---
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            email = request.form.get('email') # Email is now mandatory

            if not username or not password or not email:
                flash('Username, email, and password are required.', 'danger')
                return redirect(url_for('register'))

            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash('Username already exists. Please choose a different one.', 'warning')
                return redirect(url_for('register'))
            
            existing_email_user = User.query.filter_by(email=email).first()
            if existing_email_user:
                flash('This email address is already registered. Please use a different one or log in.', 'warning')
                return redirect(url_for('register'))

            hashed_password = generate_password_hash(password)
            new_user = User(username=username, password_hash=hashed_password, email=email, email_verified=False)
            
            try:
                db.session.add(new_user)
                db.session.commit() # Commit to get user ID if needed, or can be done after token

                token = new_user.get_email_verification_token()
                new_user.email_verification_token = token # Store the token if you need to resend or track it
                db.session.commit()

                # Send verification email
                verify_url = url_for('verify_email_route', token=token, _external=True) # Changed route name for clarity
                msg_subject = "Confirm Your Email Address - GVIM Chemistry Assistant"
                msg_body = f"Welcome to GVIM Chemistry Assistant!\n\nPlease click the following link to verify your email address:\n{verify_url}\n\nIf you did not request this, please ignore this email."
                msg_html = f"""
                <p>Welcome to GVIM Chemistry Assistant!</p>
                <p>Thanks for signing up. Please click the link below to verify your email address:</p>
                <p><a href='{verify_url}'>{verify_url}</a></p>
                <p>This link will expire in 30 minutes.</p>
                <p>If you did not request this, please ignore this email.</p>
                """
                
                message = Message(subject=msg_subject, recipients=[new_user.email], body=msg_body, html=msg_html)
                
                try:
                    mail.send(message)
                    logger.info(f"User {username} registered. Verification email sent to {email}.")
                    flash('Registration successful! A verification email has been sent. Please check your inbox to activate your account.', 'success')
                except Exception as mail_error:
                    logger.error(f"Failed to send verification email to {email} for user {username}: {mail_error}")
                    # Rollback user creation if email sending fails and it's critical
                    # db.session.delete(new_user)
                    # db.session.commit()
                    flash('Registration successful, but failed to send verification email. Please contact support or try registering again later.', 'warning')
                
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback() 
                logger.error(f"Database error during registration for user {username}: {e}")
                flash('An error occurred during registration. Please try again later.', 'danger')
                return redirect(url_for('register'))

        return render_template('register.html')

    @app.route('/verify_email/<token>') # Renamed for consistency, ensure url_for matches
    def verify_email_route(token): # Renamed function for clarity
        email = User.verify_email_token(token) # Token includes expiration check
        if email is None:
            flash('The verification link is invalid or has expired.', 'danger')
            return redirect(url_for('login')) # Or a page to resend verification
        
        user = User.query.filter_by(email=email).first()
        if user is None:
            flash('User not found for this verification link.', 'danger') # Should not happen if token is valid
            return redirect(url_for('register'))

        if user.email_verified:
            flash('Account already verified. Please log in.', 'info')
        else:
            user.email_verified = True
            user.email_verification_token = None # Clear the token once used
            try:
                db.session.commit()
                flash('Your email has been verified! You can now log in.', 'success')
                logger.info(f"Email verified for user {user.username} ({email}).")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Database error during email verification for {user.username}: {e}")
                flash('An error occurred while verifying your email. Please try again or contact support.', 'danger')
        return redirect(url_for('login'))


    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username_or_email = request.form.get('username') # Assuming 'username' field can take username or email
            password = request.form.get('password')

            if not username_or_email or not password:
                flash('Username/Email and password are required.', 'danger')
                return redirect(url_for('login'))

            user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email)).first()

            if user and check_password_hash(user.password_hash, password):
                if not user.email_verified:
                    flash('Your email address has not been verified. Please check your inbox for the verification link.', 'warning')
                    # Optionally, add a link/button here to resend verification email
                    # E.g., flash(Markup('Your email is not verified. <a href="/resend_verification/{user.email}">Resend link?</a>'), 'warning')
                    return redirect(url_for('login'))
                
                session['user_id'] = user.id 
                session['username'] = user.username 
                flash('Login successful!', 'success') # MODIFIED TO ENGLISH
                logger.info(f"User {user.username} (ID: {user.id}) logged in successfully.")
                return redirect(url_for('index'))
            else:
                flash('Invalid username/email or password.', 'danger')
                logger.warning(f"Login attempt failed for {username_or_email}: Invalid credentials.")
                return redirect(url_for('login'))
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        user_id = session.pop('user_id', None)
        username = session.pop('username', None) 
        flash('You have been logged out.', 'info') # Standard English message
        if username:
            logger.info(f"User {username} (ID: {user_id}) logged out.")
        else:
            logger.info("An unauthenticated user attempted to log out or session expired.")
        return redirect(url_for('login'))

    @app.route('/get_current_user')
    def get_current_user_route():
        if 'user_id' in session and 'username' in session: 
            return jsonify({'username': session.get('username')})
        return jsonify({'username': None}), 401

    # --- End Authentication Routes ---

    @app.route('/browser_status', methods=['GET'])
    def browser_status():
        return jsonify({
            "browser_use_available": browser_use_available,
            "playwright_installed": check_playwright_installed(),
            "openai_api_key_set": bool(os.environ.get("OPENAI_API_KEY")),
            "status": "ready" if browser_use_available else "not_available"
        })

    def check_playwright_installed():
        try:
            import playwright # type: ignore 
            return True
        except ImportError:
            return False

    @app.route('/get_molecule_details', methods=['POST'])
    def get_molecule_details():
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        try:
            data = request.json
            smiles = data.get('smiles')
            if not smiles:
                return jsonify({"error": "No SMILES provided"}), 400

            molecule_data = molecule_validator.process_smiles(smiles)
            if molecule_data is None:
                return jsonify({"error": "Invalid SMILES string"}), 400

            mol = Chem.MolFromSmiles(molecule_data["smiles"])
            if mol is None: 
                return jsonify({"error": "Invalid SMILES string (RDKit check failed)"}), 400

            mol = Chem.AddHs(mol)
            AllChem.EmbedMolecule(mol, randomSeed=42) 
            AllChem.MMFFOptimizeMolecule(mol) 
            
            conf = mol.GetConformer() 
            atoms = []
            for i, atom_obj in enumerate(mol.GetAtoms()): 
                pos = conf.GetAtomPosition(i)
                atoms.append({
                    "elem": atom_obj.GetSymbol(), 
                    "x": pos.x, 
                    "y": pos.y,
                    "z": pos.z
                })
                
            molecule_data["atoms"] = atoms 
            molecule_data["pdb"] = Chem.MolToPDBBlock(mol) 

            return jsonify(molecule_data)

        except Exception as e:
            logger.error(f"Error getting molecule details: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/get_molecule_info', methods=['POST'])
    def get_molecule_info():
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        try:
            data = request.json
            smiles = data.get('smiles')
            if not smiles:
                return jsonify({"error": "No SMILES provided"}), 400
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return jsonify({"error": "Invalid SMILES string"}), 400
            info = {
                "formula": Chem.rdMolDescriptors.CalcMolFormula(mol),
                "molecular_weight": round(Descriptors.ExactMolWt(mol), 2),
                "num_atoms": mol.GetNumAtoms(),
                "num_bonds": mol.GetNumBonds(),
                "num_rings": rdMolDescriptors.CalcNumRings(mol),
                "charge": Chem.GetFormalCharge(mol),
                "logP": round(Descriptors.MolLogP(mol), 2),
                "TPSA": round(Descriptors.TPSA(mol), 2),
                "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol)
            }
            return jsonify(info)
        except Exception as e:
            logger.error(f"Error getting molecule info: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/process_smiles', methods=['POST'])
    def process_smiles_route():
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        try:
            data = request.json
            smiles_input = data.get('smiles')
            if not smiles_input:
                return jsonify({"error": "No SMILES provided"}), 400
            result = process_smiles(smiles_input)
            if result is None:
                return jsonify({"error": "Invalid SMILES string"}), 400
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error processing SMILES: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/render_3d_structure', methods=['POST'])
    def render_3d_structure():
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        try:
            data = request.json
            smiles = data.get('smiles')
            if not smiles:
                return jsonify({"error": "No SMILES provided"}), 400
            structure = process_smiles_for_3d(smiles)
            if structure is None:
                return jsonify({"error": "Failed to generate 3D structure"}), 400
            return jsonify({"structure": structure})
        except Exception as e:
            logger.error(f"Error rendering 3D structure: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/generate_molecule_image', methods=['GET'])
    def generate_molecule_image():
        smiles = request.args.get('smiles')
        if not smiles:
            return jsonify({"error": "No SMILES provided"}), 400
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return jsonify({"error": "Invalid SMILES string"}), 400
            img = Draw.MolToImage(mol)
            img_io = io.BytesIO()
            img.save(img_io, 'PNG')
            img_io.seek(0)
            return send_file(img_io, mimetype='image/png')
        except Exception as e:
            logger.error(f"Error generating molecule image: {str(e)}")
            return jsonify({"error": str(e)}), 400

    @app.route('/configure', methods=['POST'])
    def configure():
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        nonlocal chemistry_lab 
        data = request.json
        literature_path_nonlocal["path"] = data.get('literature_path', '')
        web_url_path_nonlocal["path"] = data.get('web_url_path', '')
        chemistry_lab = get_chemistry_lab(literature_path_nonlocal["path"])
        logger.info(f"Configured with literature_path: {literature_path_nonlocal['path']}, web_url_path: {web_url_path_nonlocal['path']}")
        return jsonify({'status': 'Configuration updated', 'literature_path': literature_path_nonlocal["path"]})

    @app.route('/simulate', methods=['POST'])
    def simulate():
        if 'user_id' not in session:
            return jsonify([{'role': 'assistant', 'name': 'System', 'content': 'Authentication required. Please log in.'}]), 401
        
        # Get the chemistry lab instance
        nonlocal chemistry_lab
        if not chemistry_lab:
            chemistry_lab = get_chemistry_lab(literature_path_nonlocal["path"])

        user_input_text = request.form.get('message', '')
        image_file_obj = request.files.get('image')
        new_literature_path_val = request.form.get('literature_path', '')
        new_web_url_path_val = request.form.get('web_url_path', '')
        session_id_val = session.get('username', f"guest_{random.randint(1000,9999)}")
        
        logger.info(f"Received request - User input: {user_input_text[:50]}..., Literature path: {new_literature_path_val}, Web URL path: {new_web_url_path_val}, Session ID: {session_id_val}")
        request.start_time = time.time()

        # Update literature path if necessary
        current_literature_path = literature_path_nonlocal["path"]
        if new_literature_path_val and new_literature_path_val != current_literature_path:
            logger.info(f"Updating literature path from {current_literature_path} to {new_literature_path_val}")
            literature_path_nonlocal["path"] = new_literature_path_val
            chemistry_lab = get_chemistry_lab(literature_path_nonlocal["path"])
        
        web_url_path_nonlocal["path"] = new_web_url_path_val
        
        image_data_bytes = None
        image_data_b64_for_history = None

        try:
            search_results = []
            llava_response = None
            
            # Process image if provided
            if image_file_obj:
                try:
                    image_data_bytes = image_file_obj.read()
                    image_data_b64_for_history = base64.b64encode(image_data_bytes).decode('utf-8')
                    logger.info(f"Image received: {image_file_obj.filename}, size: {len(image_data_bytes)} bytes")
                    llava_response = llava_call(user_input_text, image_data_bytes, llava_config_list[0])
                    logger.info(f"LLaVA Response: {llava_response}")
                    combined_query = f"{user_input_text} {llava_response}"
                    search_results = tavily_search(combined_query, url=web_url_path_nonlocal["path"]) if web_url_path_nonlocal["path"] and is_valid_url(web_url_path_nonlocal["path"]) else tavily_search(combined_query)
                except Exception as e:
                    logger.error(f"Error in image processing: {str(e)}")
                    llava_response = f"Error processing image: {str(e)}"
            else:
                try:
                    search_results = tavily_search(user_input_text, url=web_url_path_nonlocal["path"]) if web_url_path_nonlocal["path"] and is_valid_url(web_url_path_nonlocal["path"]) else tavily_search(user_input_text)
                except Exception as e:
                    logger.error(f"Error in web search: {str(e)}")
            
            # RAG search if available
            rag_results = None
            if chemistry_lab and hasattr(chemistry_lab, 'db') and chemistry_lab.db:
                try:
                    # from simulate_ai import rag_search 
                    # rag_results = rag_search(user_input_text, chemistry_lab.db) 
                    logger.info("RAG search skipped (if rag_search not implemented or imported).")
                    pass
                except NameError:
                    logger.warning("rag_search function not defined or imported.")
                except Exception as e:
                    logger.error(f"Error in RAG search: {str(e)}")

            # Process user input through chemistry lab
            response_messages_list = chemistry_lab.process_user_input(
                user_input_text,
                image_data=image_data_bytes,
                literature_path=literature_path_nonlocal["path"],
                web_url_path=web_url_path_nonlocal["path"]
            )
            
            # Simulate for agent evolution
            chemistry_lab.simulate(1)
            
            # Analyze performance
            performance_analysis_data = chemistry_lab.analyze_system_performance()
            updated_agents_list = [{'name': agent.name, 'evolutionLevel': agent.evolution_level, 'skills': list(agent.skills)} for agent in chemistry_lab.agents]
            
            # Process response messages
            first_assistant_found = False
            feedback_data = {}
            for msg in response_messages_list:
                if msg.get('role') == 'assistant':
                    if msg.get('feedback_rating'):
                        feedback_data[msg.get('name', 'unknown')] = {'rating': msg['feedback_rating'], 'timestamp': datetime.now().isoformat()}
                    if not first_assistant_found:
                        first_assistant_found = True
                        if llava_response:
                            msg['content'] = f"Image Analysis: {llava_response}\n\n{msg['content']}"
                        processed_s_results_list = [] 
                        if search_results:
                            web_res = process_search_results(search_results) 
                            if web_res:
                                processed_s_results_list.append({'type': 'web', 'results': web_res})
                        if rag_results:
                            rag_proc = process_search_results([{'content': rag_results, 'title': 'Literature Search Result', 'url': None}]) 
                            if rag_proc:
                                processed_s_results_list.append({'type': 'rag', 'results': rag_proc})
                        if processed_s_results_list:
                            msg['search_results'] = processed_s_results_list
            
            # Add performance analysis to the response
            response_messages_list.append({'role': 'system', 'name': 'Performance_Analysis', 'content': json.dumps({'performance_analysis': performance_analysis_data, 'updated_agents': updated_agents_list})})
            
            # Store chat history
            history_entry_data = {
                'timestamp': datetime.now().isoformat(), 
                'session_id': session_id_val, 
                'user_input': user_input_text,
                'image_data': image_data_b64_for_history, 
                'literature_path': literature_path_nonlocal["path"], 
                'web_url_path': web_url_path_nonlocal["path"],
                'response': response_messages_list, 
                'feedback': feedback_data,
                'files': {
                    'image': bool(image_data_b64_for_history), 
                    'literature': bool(literature_path_nonlocal["path"]), 
                    'web_url': bool(web_url_path_nonlocal["path"])
                },
                'performance_metrics': {
                    'response_time': time.time() - request.start_time if hasattr(request, 'start_time') else None,
                    'agent_updates': len(updated_agents_list),
                    'search_results_count': len(search_results) if search_results else 0
                }
            }
            
            try:
                chat_storage.add_session_entry(session_id_val, history_entry_data)
            except Exception as storage_error:
                logger.error(f"Error storing chat history: {str(storage_error)}")
                
            return jsonify(response_messages_list)
            
        except Exception as e:
            logger.error(f"Error processing user input: {str(e)}", exc_info=True)
            error_response_msg = [{'role': 'assistant', 'name': 'System', 'content': f"Error processing your input: {str(e)}"}]
            
            # Log error to chat history
            error_entry = {
                'timestamp': datetime.now().isoformat(), 
                'session_id': session_id_val, 
                'user_input': user_input_text,
                'image_data': image_data_b64_for_history, 
                'literature_path': literature_path_nonlocal["path"], 
                'web_url_path': web_url_path_nonlocal["path"],
                'response': error_response_msg, 
                'feedback': {},
                'files': {
                    'image': bool(image_data_b64_for_history), 
                    'literature': bool(literature_path_nonlocal["path"]), 
                    'web_url': bool(web_url_path_nonlocal["path"])
                },
                'error': {'message': str(e), 'traceback': traceback.format_exc()}
            }
            
            try:
                chat_storage.add_session_entry(session_id_val, error_entry)
            except Exception as storage_error:
                logger.error(f"Error storing error history: {str(storage_error)}")
                
            return jsonify(error_response_msg), 500

    @app.route('/render_3d_molecule', methods=['POST'])
    def render_3d_molecule():
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        try:
            data = request.json
            smiles = data.get('smiles')
            if not smiles:
                return jsonify({"error": "No SMILES provided"}), 400
            mol_structure = process_smiles_for_3d(smiles)
            if mol_structure is None:
                return jsonify({"error": "Failed to process SMILES"}), 400
            return jsonify(mol_structure)
        except Exception as e:
            logger.error(f"Error rendering 3D molecule: {str(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route('/initialize', methods=['POST'])
    def initialize_chat():
        if 'user_id' not in session:
            return jsonify({'status': 'Authentication required'}), 401
        nonlocal chemistry_lab
        chemistry_lab = get_chemistry_lab(literature_path_nonlocal["path"]) 
        return jsonify({'status': 'Chemistry Lab initialized successfully'})

    @app.route('/feedback', methods=['POST'])
    def feedback():
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        try:
            feedback_data_req = request.json
            if not feedback_data_req:
                return jsonify({'error': 'No feedback data provided'}), 400
            session_id_val = request.args.get('session_id', session.get('username', 'default'))
            try:
                message_index = int(request.args.get('message_index', -1))
            except ValueError:
                return jsonify({'error': 'Invalid message index'}), 400
            success = chat_storage.add_feedback(session_id_val, message_index, feedback_data_req)
            if success:
                return jsonify({'status': 'Feedback received and stored successfully'})
            else:
                return jsonify({'error': 'Failed to save feedback'}), 400
        except Exception as e:
            logger.error(f"Error processing feedback: {str(e)}")
            return jsonify({'error': str(e)}), 400

    @app.route('/history', methods=['GET'])
    def history():
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        try:
            session_id_req = request.args.get('session_id', session.get('username'))
            history_data = chat_storage.get_session_history(session_id_req)
            if session_id_req == 'all':
                if 'sessions' in history_data:
                    for hist_s in history_data['sessions']: 
                        if 'response' in hist_s and 'feedback' in hist_s:
                            for msg_item in hist_s['response']: 
                                if msg_item.get('role') == 'assistant' and hist_s.get('feedback'):
                                    agent_name_val = msg_item.get('name') 
                                    if agent_name_val and agent_name_val in hist_s['feedback']:
                                        msg_item['feedback_rating'] = hist_s['feedback'][agent_name_val]
            else:
                if 'session' in history_data:
                     for hist_e in history_data['session']: 
                        if 'response' in hist_e and 'feedback' in hist_e:
                            for msg_item in hist_e['response']: 
                                if msg_item.get('role') == 'assistant' and hist_e.get('feedback'):
                                    agent_name_val = msg_item.get('name') 
                                    if agent_name_val and agent_name_val in hist_e['feedback']:
                                        msg_item['feedback_rating'] = hist_e['feedback'][agent_name_val]
            return jsonify(history_data)
        except Exception as e:
            logger.error(f"Error retrieving history: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/chemical_purchase', methods=['POST'])
    def chemical_purchase():
        if 'user_id' not in session: 
            return jsonify({"error": "Authentication required"}), 401
        try:
            data = request.json
            supplier = data.get('supplier')
            items = data.get('items', [])
            
            if not supplier or not items:
                return jsonify({"error": "Supplier and item list are required"}), 400 # English message
            
            from browser_automation import execute_chemical_purchase 
            logger.info(f"User {session.get('username')} starting automated chemical purchase for supplier {supplier}")
            
            try:
                result = execute_chemical_purchase(supplier, items)
                if result.get("status") == "success":
                    logger.info(f"Browser automation successful: {result}")
                    if "agent_result" in result:
                        agent_res = result.pop("agent_result") 
                        result["agent_summary"] = str(agent_res)[:200] + "..." if len(str(agent_res)) > 200 else str(agent_res)
                    return jsonify(result)
                else:
                    logger.warning(f"Automation returned error: {result}")
                    return jsonify(result), 400
            except Exception as e:
                logger.error(f"Browser automation error: {str(e)}")
                logger.info("Falling back to simulated purchase")
                time.sleep(random.uniform(1, 3))
                order_id_val = f"ORD-SIM-{random.randint(10000, 99999)}" 
                total_price_val = sum([random.uniform(10, 200) for _ in items]) 
                est_delivery_days = random.randint(3, 7) 
                est_delivery_date = (datetime.now() + timedelta(days=est_delivery_days)).strftime("%Y-%m-%d") 
                est_delivery_str = f"{est_delivery_days} business days (Est. {est_delivery_date})" 
                item_details_list = [] 
                for item_val in items: 
                    parts_list = item_val.split(' ', 1) 
                    qty_str = parts_list[0] if len(parts_list) > 1 else "1" 
                    name_str = parts_list[1] if len(parts_list) > 1 else parts_list[0] 
                    cas_str = f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(0, 9)}" 
                    item_details_list.append({"name": name_str, "quantity": qty_str, "cas": cas_str, "price": round(random.uniform(10, 100), 2)})
                response_data_dict = { 
                    "status": "success_simulated", "supplier": supplier, "items": item_details_list,
                    "order_id": order_id_val, "total_price": round(total_price_val, 2),
                    "estimated_delivery": est_delivery_str, "note": "Simulated response due to automation error.", # English
                    "error_details": str(e)
                }
                return jsonify(response_data_dict)
        except Exception as e:
            logger.error(f"Chemical purchase error: {str(e)}")
            return jsonify({"error": str(e)}), 500
        
    @app.route('/')
    def index():
        if 'user_id' not in session: 
            return redirect(url_for('login'))
        return send_from_directory(app.static_folder, 'index.html')

    @app.route('/static/<path:path>')
    def send_static(path):
        return send_from_directory(app.static_folder, path)

    @app.route('/get_3d_structure', methods=['POST'])
    def get_3d_structure():
        if 'user_id' not in session: 
            return jsonify({"error": "Authentication required"}), 401
        try:
            data = request.json
            smiles = data.get('smiles')
            if not smiles:
                return jsonify({"error": "No SMILES provided"}), 400
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return jsonify({"error": "Invalid SMILES string"}), 400
            mol = Chem.AddHs(mol)
            AllChem.EmbedMolecule(mol, randomSeed=42)
            AllChem.MMFFOptimizeMolecule(mol)
            conf = mol.GetConformer()
            structure = {
                "atoms": [{"serial": i + 1, "elem": atom.GetSymbol(), "x": conf.GetAtomPosition(i).x, "y": conf.GetAtomPosition(i).y, "z": conf.GetAtomPosition(i).z} for i, atom in enumerate(mol.GetAtoms())],
                "bonds": [{"start": bond.GetBeginAtomIdx() + 1, "end": bond.GetEndAtomIdx() + 1, "order": int(bond.GetBondTypeAsDouble())} for bond in mol.GetBonds()]
            }
            return jsonify({"structure": structure})
        except Exception as e:
            logger.error(f"Error getting 3D structure: {str(e)}")
            return jsonify({"error": str(e)}), 500

    socketio = SocketIO(app)

    @socketio.on('connect')
    def handle_connect():
        if 'user_id' not in session: 
            logger.info('Unauthenticated client tried to connect via WebSocket.')
        else:
            logger.info(f'Client {session.get("username", "Unknown")} (ID: {session["user_id"]}) connected via WebSocket.')

    @socketio.on('disconnect')
    def handle_disconnect():
        username = session.get("username", "Unknown client")
        user_id = session.get("user_id", "Unknown ID")
        logger.info(f'Client {username} (ID: {user_id}) disconnected from WebSocket.')

    return app, socketio

if __name__ == '__main__':
    app_instance, socketio_instance = create_app() 
    # When running locally for development, you might want to set debug=True
    # For production, debug should be False.
    # allow_unsafe_werkzeug=True is generally for development when using the Werkzeug reloader with SSL or complex setups.
    # Consider using a production-ready WSGI server like Gunicorn or uWSGI behind a reverse proxy (like Nginx) for deployment.
    socketio_instance.run(app_instance, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true', host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True if os.environ.get('FLASK_DEBUG', 'False').lower() == 'true' else False)