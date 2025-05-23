import json
import os
import random
import re
import base64
import io
import warnings
import logging
from collections import deque
from typing import List, Dict, Any, Union, Set, Optional
from dataclasses import dataclass
from functools import lru_cache
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.io as pio
import autogen
from autogen import Agent, AssistantAgent, ConversableAgent, UserProxyAgent
from autogen.agentchat.contrib.llava_agent import LLaVAAgent
import replicate
from PIL import Image
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import CharacterTextSplitter
from langchain_openai import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain.agents import Tool
from tavily import TavilyClient
from rdkit import Chem
from rdkit.Chem import AllChem, Draw, Descriptors, rdMolDescriptors
from tenacity import retry, stop_after_attempt, wait_fixed
import numpy as np
from scipy import stats
import py3Dmol

warnings.filterwarnings("ignore")
# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

os.environ["TAVILY_API_KEY"] = ""
os.environ["REPLICATE_API_TOKEN"] = ""  # Replace with your actual token

config_list = [
    {
        "model": "llama3-70b-8192",
        "api_key": "",
        "base_url": "https://api.groq.com/openai/v1"
    },
    {
        "model": "MistralNemo",
        "api_key": "NA",
        "base_url": "https://39ac-34-143-242-101.ngrok-free.app/api"
    },
    {
        "model": "mixtral-8x7b-32768",
        "api_key": "",
        "base_url": "https://api.groq.com/openai/v1"
    },
]

llava_config_list = [
    {
        "model": "whatever, will be ignored for remote",
        "api_key": "None",
        "base_url": "yorickvp/llava-13b:80537f9eead1a5bfa72d5ac6ea6414379be41d4d4f6679fd776e9535d1eb58bb",
    }
]
@dataclass
class WordFilter:
    """Filter for identifying common English words and patterns"""
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        # File formats
        self.file_formats = {
            'PDF', 'DOC', 'DOCX', 'XLS', 'XLSX', 'CSV', 'TXT', 'RTF', 'PPT', 'PPTX',
            'PDB', 'MOL', 'SDF', 'CIF', 'INP', 'OUT', 'LOG'
        }
        
        # Common abbreviations and technical terms
        self.common_abbreviations = {
            'DNA', 'RNA', 'ATP', 'ADP', 'NAD', 'FAD', 'GDP', 'GTP',  # Biochemistry
            'NMR', 'IR', 'MS', 'UV', 'CD', 'GC', 'HPLC', 'TLC',      # Analytical methods
            'PDF', 'DOI', 'ISBN', 'ISSN', 'URL', 'HTTP', 'FTP',      # Literature
            'ID', 'PIN', 'PID', 'CEO', 'CFO', 'CTO', 'PhD',          # General
            'AM', 'PM', 'EST', 'PST', 'UTC', 'GMT',                  # Time
            'USA', 'UK', 'EU', 'UN', 'WHO', 'NASA',                  # Organizations
        }
        
        # Common chemistry terms (not SMILES)
        self.chemistry_terms = {
            'pH', 'pKa', 'pKb', 'eV', 'HOMO', 'LUMO',                # Chemistry concepts
            'Vol', 'Mol', 'Mass', 'Conc',                            # Measurements
            'Lab', 'Test', 'Study', 'Data', 'Plot', 'Graph',         # Experimental
            'Page', 'Fig', 'Table', 'Ref', 'Cite',                   # Document elements
        }
        
        # Common units
        self.units = {
            'mg', 'kg', 'mL', 'L', 'mol', 'M', 'mM', 'µM', 'nM',    # Basic units
            'Hz', 'MHz', 'GHz', 'V', 'mV', 'A', 'mA', 'W', 'kW',    # Physical units
            'Pa', 'kPa', 'bar', 'atm', 'torr', 'psi',               # Pressure units
            '°C', '°F', 'K',                                         # Temperature units
        }
        
        # Common English word suffixes
        self.word_suffixes = {
            'ing', 'ed', 'es', 's', 'er', 'est', 'ly', 'ment', 'ness', 'ion',
            'tion', 'sion', 'ity', 'ty', 'ism', 'ist', 'ic', 'al', 'ous', 'ful',
            'able', 'ible', 'less', 'ive', 'ize', 'ise', 'ify', 'fy'
        }
        
        # Combine all patterns
        patterns = [
            r'\b[A-Z][a-z]{2,}\b',            # Capitalized words
            r'\b[a-z]{2,}\b',                 # Lowercase words
            r'\b(?:' + '|'.join(self.file_formats) + r')\b',
            r'\b(?:' + '|'.join(self.common_abbreviations) + r')\b',
            r'\b(?:' + '|'.join(self.chemistry_terms) + r')\b',
            r'\b\d*\.?\d+\s*(?:' + '|'.join(self.units) + r')\b',
            r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b',    # Dates
            r'\b\d{1,2}:\d{1,2}(?::\d{1,2})?\b',     # Times
            r'[,.;:!?"\']',                          # Punctuation
            r'[\u2018-\u201F]',                      # Smart quotes
            r'\b[A-Z]+s?\b(?<!S)(?<!Cl)(?<!Br)',    # All caps (excluding elements)
            r'\b(?:https?://)?(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?\b',  # URLs
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Emails
            r'\b\d+(?:\.\d+)?\b',                    # Numbers
            r'\b[A-Za-z]\d+\b',                      # Code numbers
            r'\b(?:in|on|at|to|for|of|by|with)\s+\w+\b',  # Prepositions
            r'\b(?:the|a|an)\s+\w+\b',                    # Articles
        ]
        
        self.word_pattern = re.compile('|'.join(patterns), re.IGNORECASE)
    
    def is_common_word(self, text: str) -> bool:
        """Check if text matches common word patterns"""
        return bool(self.word_pattern.match(text))
    
    def contains_word_suffix(self, text: str) -> bool:
        """Check if text contains common English word suffixes"""
        return any(text.lower().endswith(suffix) for suffix in self.word_suffixes)
    
class MoleculeValidator:
    """A comprehensive validator for molecules, combining InorganicCompoundValidator and SmilesValidator"""
    
    def __init__(self):
        self._setup_elements()
        self._setup_patterns()
        self._setup_common_ions()
        self._validation_cache = {}

    def clean_smiles(self, smiles: str) -> Optional[str]:
        try:
            # Remove any whitespace
            smiles = smiles.strip()
            
            # Check for unclosed rings
            ring_numbers = re.findall(r'%?\d+', smiles)
            ring_count = {}
            for num in ring_numbers:
                num = num.lstrip('%')
                ring_count[num] = ring_count.get(num, 0) + 1
                
            # If any ring number appears only once, try to fix or return None
            for num, count in ring_count.items():
                if count % 2 != 0:
                    return None
                    
            mol = Chem.MolFromSmiles(smiles, sanitize=False)
            if mol is None:
                return None
                
            try:
                Chem.SanitizeMol(mol)
                return Chem.MolToSmiles(mol, canonical=True)
            except:
                return None
                
        except Exception as e:
            logger.error(f"Error cleaning SMILES: {str(e)}")
            return None
    
    def process_smiles(self, smiles: str) -> Optional[Dict]:
        """Process SMILES string and return molecule properties"""
        try:
            # Clean and validate SMILES first
            cleaned_smiles = self.clean_smiles(smiles)
            if cleaned_smiles is None:
                return None

            mol = Chem.MolFromSmiles(cleaned_smiles, sanitize=False)
            if mol is None:
                return None

            try:
                Chem.SanitizeMol(mol)
            except:
                return None

            return {
                "formula": Chem.rdMolDescriptors.CalcMolFormula(mol),
                "molecular_weight": round(Descriptors.ExactMolWt(mol), 2), 
                "num_atoms": mol.GetNumAtoms(),
                "num_bonds": mol.GetNumBonds(),
                "num_rings": rdMolDescriptors.CalcNumRings(mol),
                "charge": Chem.GetFormalCharge(mol),
                "logP": round(Descriptors.MolLogP(mol), 2),
                "TPSA": round(Descriptors.TPSA(mol), 2), 
                "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol),
                "smiles": cleaned_smiles
            }

        except Exception as e:
            logger.error(f"Error processing SMILES: {str(e)}")
            return None
        
    def _setup_elements(self):
        """Set up periodic table elements and their properties"""
        self.metals = {
            'Li', 'Na', 'K', 'Rb', 'Cs', 'Fr',  # Alkali metals
            'Be', 'Mg', 'Ca', 'Sr', 'Ba', 'Ra',  # Alkaline earth metals
            'Sc', 'Ti', 'V', 'Cr', 'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn',  # Transition metals
            'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd',
            'La', 'Hf', 'Ta', 'W', 'Re', 'Os', 'Ir', 'Pt', 'Au', 'Hg',
            'Al', 'Ga', 'In', 'Sn', 'Tl', 'Pb', 'Bi'  # Post-transition metals
        }
        
        self.non_metals = {
            'H', 'C', 'N', 'O', 'P', 'S', 'Se',  # Non-metals
            'F', 'Cl', 'Br', 'I', 'At',  # Halogens
            'He', 'Ne', 'Ar', 'Kr', 'Xe', 'Rn',  # Noble gases
            'B', 'Si', 'Ge', 'As', 'Sb', 'Te'  # Metalloids
        }
        
        # Common oxidation states
        self.oxidation_states = {
            'Na': [1], 'K': [1], 'Mg': [2], 'Ca': [2], 'Al': [3],
            'Fe': [2, 3], 'Cu': [1, 2], 'Ag': [1], 'Zn': [2],
            'H': [1, -1], 'O': [-2], 'Cl': [-1, 1, 3, 5, 7],
            'S': [-2, 4, 6], 'N': [-3, 3, 5], 'P': [-3, 3, 5],
            'C': [-4, 2, 4], 'B': [3]
        }

    def _setup_common_ions(self):
        """Set up common polyatomic ions"""
        self.common_anions = {
            'OH': -1,     # Hydroxide
            'CN': -1,     # Cyanide
            'NO3': -1,    # Nitrate
            'NO2': -1,    # Nitrite
            'CO3': -2,    # Carbonate
            'SO4': -2,    # Sulfate
            'SO3': -2,    # Sulfite
            'PO4': -3,    # Phosphate
            'ClO': -1,    # Hypochlorite
            'ClO2': -1,   # Chlorite
            'ClO3': -1,   # Chlorate
            'ClO4': -1,   # Perchlorate
            'CH3COO': -1, # Acetate
            'HCO3': -1,   # Bicarbonate
            'HSO4': -1,   # Bisulfate
            'NH4': 1,     # Ammonium
            'H3O': 1      # Hydronium
        }

    def _setup_patterns(self):
        """Set up regex patterns for validation"""
        # Pattern for element with optional number
        element_pattern = r'(?:[A-Z][a-z]?\d*)'
        
        # Pattern for SMILES validation
        self.smiles_pattern = re.compile(
            r'^[A-Za-z0-9@+\-\[\]\(\)\\/%=#$.,*~{}:]+$'
        )
        
        # Pattern for molecule validation
        self.molecule_pattern = re.compile(
            r'^(?:[A-Z][a-z]?\d*)+$'
        )

    def is_valid_molecule(self, molecule: str) -> bool:
        """
        Validate if the given string represents a valid molecule structure
        
        Args:
            molecule (str): Molecule string to validate
            
        Returns:
            bool: True if valid molecule structure
        """
        if molecule in self._validation_cache:
            return self._validation_cache[molecule]
            
        try:
            # Remove spaces and normalize
            molecule = molecule.strip().replace(' ', '')
            
            # Basic pattern matching
            if not self.molecule_pattern.match(molecule):
                return False
                
            # Check if it's a valid SMILES string
            mol = Chem.MolFromSmiles(molecule)
            if mol is None:
                return False
                
            # Additional validation rules can be added here
            result = True
            
        except Exception as e:
            logging.debug(f"Error validating molecule {molecule}: {str(e)}")
            result = False
            
        self._validation_cache[molecule] = result
        return result

    def is_valid_smiles(self, smiles: str) -> bool:
        """
        Validate if the given string is a valid SMILES representation
        
        Args:
            smiles (str): SMILES string to validate
            
        Returns:
            bool: True if valid SMILES
        """
        if smiles in self._validation_cache:
            return self._validation_cache[smiles]
            
        try:
            # Basic pattern matching
            if not self.smiles_pattern.match(smiles):
                return False
                
            # Check structure using RDKit
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return False
                
            # Validate molecule sanity
            try:
                Chem.SanitizeMol(mol)
            except Exception:
                return False
                
            result = True
            
        except Exception as e:
            logging.debug(f"Error validating SMILES {smiles}: {str(e)}")
            result = False
            
        self._validation_cache[smiles] = result
        return result

    def get_molecule_info(self, molecule: str) -> Optional[Dict]:
        """
        Get detailed information about a molecule
        
        Args:
            molecule (str): Molecule string or SMILES
            
        Returns:
            Optional[Dict]: Molecule information or None if invalid
        """
        if not self.is_valid_molecule(molecule) and not self.is_valid_smiles(molecule):
            return None
            
        try:
            mol = Chem.MolFromSmiles(molecule)
            if mol is None:
                return None
                
            info = {
                'formula': Chem.rdMolDescriptors.CalcMolFormula(mol),
                'num_atoms': mol.GetNumAtoms(),
                'num_bonds': mol.GetNumBonds(),
                'is_aromatic': any(atom.GetIsAromatic() for atom in mol.GetAtoms()),
                'elements': [],
                'formal_charge': Chem.GetFormalCharge(mol)
            }
            
            # Get unique elements
            elements = set()
            for atom in mol.GetAtoms():
                elements.add(atom.GetSymbol())
            info['elements'] = sorted(list(elements))
            
            return info
            
        except Exception as e:
            logging.debug(f"Error getting molecule info for {molecule}: {str(e)}")
            return None

class SmilesValidator:
    """SMILES string validator with integrated word filtering"""
    
    def __init__(self):
        self.word_filter = WordFilter()
        self._compile_patterns()
        self._validation_cache = {}
    
    def _compile_patterns(self):
        # Valid atom symbols
        self.VALID_ATOMS = {
            # Common organic atoms
            'C', 'N', 'O', 'P', 'S', 'F', 'Cl', 'Br', 'I', 'B',
            # Metal atoms
            'Na', 'K', 'Li', 'Ca', 'Mg', 'Al', 'Fe', 'Zn', 'Cu', 'Ag', 'Au', 'Pt',
            # Aromatic atoms
            'c', 'n', 'o', 'p', 's'
        }
        
        # SMILES specific symbols
        self.SMILES_SYMBOLS = set('-=#$.:/\\()[]{}~@+*')
        
        # Compile SMILES pattern
        atoms = '|'.join(sorted(self.VALID_ATOMS, key=len, reverse=True))
        symbols = re.escape(''.join(self.SMILES_SYMBOLS))
        self.smiles_pattern = re.compile(
            r'\b(?:' +
            f'(?:{atoms})' +  # Initial atom
            f'(?:[{symbols}]|{atoms}|\d)*' +  # Remaining structure
            r')\b'
        )

    def _check_structural_validity(self, text: str) -> bool:
        """Perform structural checks on SMILES string"""
        # Check basic bracket balance
        bracket_count = 0
        paren_count = 0
        for char in text:
            if char == '[': bracket_count += 1
            elif char == ']': bracket_count -= 1
            elif char == '(': paren_count += 1
            elif char == ')': paren_count -= 1
            if bracket_count < 0 or paren_count < 0:
                return False
        return bracket_count == 0 and paren_count == 0
    
    def is_valid_smiles(self, text: str) -> bool:
        """Validate whether a string is a valid SMILES"""
        # Check cache
        if text in self._validation_cache:
            return self._validation_cache[text]
        
        # Basic checks
        if not text or len(text) < 2:
            self._validation_cache[text] = False
            return False
        
        # Check for common words or patterns
        if self.word_filter.is_common_word(text):
            self._validation_cache[text] = False
            return False
        
        # Check for common word suffixes
        if self.word_filter.contains_word_suffix(text):
            self._validation_cache[text] = False
            return False
        
        # Check structural validity
        if not self._check_structural_validity(text):
            self._validation_cache[text] = False
            return False
        
        # Validate using RDKit
        try:
            mol = Chem.MolFromSmiles(text)
            if mol is None:
                self._validation_cache[text] = False
                return False
                
            # Ensure molecule has sufficient complexity
            if mol.GetNumAtoms() < 2 or mol.GetNumBonds() < 1:
                self._validation_cache[text] = False
                return False
                
            # Validate molecule sanity
            try:
                Chem.SanitizeMol(mol)
                Chem.DetectBondStereochemistry(mol)
                Chem.AssignStereochemistry(mol)
            except Exception:
                self._validation_cache[text] = False
                return False
                
        except Exception as e:
            logging.debug(f"RDKit validation failed for {text}: {str(e)}")
            self._validation_cache[text] = False
            return False
        
        self._validation_cache[text] = True
        return True

class SmilesProcessor:
    """SMILES text processor with HTML formatting capabilities"""
    
    def __init__(self):
        self.validator = SmilesValidator()
        self.processed_smiles: Set[str] = set()
        self._processing_cache: Dict[str, str] = {}
    
    def format_smiles(self, smiles: str, is_first_occurrence: bool) -> str:
        """Format SMILES string for display with optional 3D view button"""
        if is_first_occurrence:
            return (
                f'<span class="molecule-ref" data-smiles="{smiles}">'
                f'{smiles}'
                f'<button class="view-3d-btn ml-2 text-sm bg-blue-500 text-white '
                f'px-2 py-1 rounded hover:bg-blue-600">View 3D</button>'
                f'</span>'
            )
        return f'<span class="smiles-text">{smiles}</span>'
    
    def process_text(self, text: str) -> str:
        """Process text to identify and format SMILES strings"""
        if not text:
            return text
        
        # Check cache
        if text in self._processing_cache:
            return self._processing_cache[text]
        
        def replace_with_markup(match):
            candidate = match.group(0)
            
            # Validate SMILES
            if not self.validator.is_valid_smiles(candidate):
                return candidate
            
            # Check for first occurrence
            is_first_occurrence = candidate not in self.processed_smiles
            if is_first_occurrence:
                self.processed_smiles.add(candidate)
            
            return self.format_smiles(candidate, is_first_occurrence)
        
        # Use validator's SMILES pattern for replacement
        processed_text = self.validator.smiles_pattern.sub(replace_with_markup, text)
        
        # Cache result
        self._processing_cache[text] = processed_text
        return processed_text
    
    def reset(self):
        """Reset processor state"""
        self.processed_smiles.clear()
        self._processing_cache.clear()

class GlobalSmilesProcessor:
    """Global SMILES processor singleton"""
    _instance = None
    _processor = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalSmilesProcessor, cls).__new__(cls)
            cls._processor = SmilesProcessor()
        return cls._instance
    
    @classmethod
    def get_processor(cls) -> SmilesProcessor:
        if cls._instance is None:
            cls._instance = cls()
        return cls._processor

def get_global_smiles_processor() -> SmilesProcessor:
    """Get global SMILES processor instance"""
    return GlobalSmilesProcessor.get_processor()

def process_smiles_in_text(text: str) -> str:
    """Global processing function for SMILES in text"""
    processor = get_global_smiles_processor()
    return processor.process_text(text)

def is_valid_url(url):
    regex = re.compile(
        r'^(?:http|ftp)s?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None

def llava_call(prompt: str, image_data: Union[bytes, None] = None, config: Dict[str, Any] = None) -> str:
    if config is None:
        config = llava_config_list[0]

    base_url = config["base_url"]

    inputs = {
        "prompt": prompt,
        "timeout": 90  # Set timeout to 90 seconds
    }

    if image_data:
        try:
            # Validate image size (max 5MB)
            if len(image_data) > 5 * 1024 * 1024:
                return "Error: Image size must be less than 5MB"
                
            # Convert image data to base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            inputs["image"] = f"data:image/jpeg;base64,{image_base64}"
            
            output = replicate.run(base_url, input=inputs)
            return "".join(output)
            
        except replicate.exceptions.ReplicateError as e:
            logger.error(f"Replicate API error: {str(e)}")
            return "Error: The model is currently busy. Please try again in a few moments."
        except Exception as e:
            logger.error(f"Error calling LLaVA API: {str(e)}")
            if "timeout" in str(e).lower():
                return "Error: Request timed out. Please try with a smaller image or try again later."
            return f"Error processing image: {str(e)}"
    else:
        try:
            output = replicate.run(base_url, input=inputs)
            return "".join(output)
        except Exception as e:
            logger.error(f"Error in LLaVA call: {str(e)}")
            return f"Error: {str(e)}"
        
def load_documents(file_path):
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return []

    if file_path.endswith('.pdf'):
        loader = PyPDFLoader(file_path)
    else:
        loader = TextLoader(file_path)

    return loader.load()

# Load experiment data
experiment_data = load_documents("E://HuaweiMoveData//Users//makangyong//Desktop//output.txt")

# Load literature (if available)
literature_path = ""  # Update this path if you have literature to load
literature = load_documents(literature_path) if literature_path else []

# Combine all documents
all_documents = experiment_data + literature

# Check if we have any documents before proceeding
if not all_documents:
    logger.warning("No documents loaded. Skipping embedding and vector store creation.")
    db = None
else:
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
    texts = text_splitter.split_documents(all_documents)

    embeddings = HuggingFaceEmbeddings()
    db = Chroma.from_documents(texts, embeddings)

llm = ChatOpenAI(model_name="llama-3.3-70b-versatile", openai_api_key=config_list[0]["api_key"], openai_api_base=config_list[0]["base_url"])
rag_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=db.as_retriever(search_kwargs={"k": 3})
)

# Initialize Tavily client with error handling and fallback
def fallback_search(query):
    logger.warning(f"Fallback search used for query: {query}")
    return f"Fallback search result for: {query}"

try:
    tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
except Exception as e:
    logger.error(f"Error initializing Tavily client: {str(e)}")
    tavily_client = None

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def tavily_search_tool_function(query: str, url: Optional[str] = None) -> Union[List[Dict[str, str]], str]: # <--- MODIFIED NAME and added type hints
    if tavily_client is None: return "Tavily client not available."
    try:
        search_params: Dict[str, Any] = {"query": query, "search_depth": "advanced", "max_results": 5, "include_answer": True}
        if url and is_valid_url(url): search_params["include_domains"] = [url]
        response = tavily_client.search(**search_params)
        results = [{"url": obj.get("url",""), "title": obj.get("title","N/A"), "content": obj.get("content","")} for obj in response.get("results",[])]
        if response.get("answer"): results.insert(0, {"title": "Tavily Answer", "content": response["answer"], "url": ""})
        return results
    except Exception as e: 
        logger.error(f"Error in Tavily search for '{query}': {e}", exc_info=True)
        return f"Error during Tavily search: {str(e)}"

def tavily_search(query: str, url: Optional[str] = None) -> Union[List[Dict[str, str]], str]:
    """Wrapper for tavily_search_tool_function to maintain backward compatibility"""
    return tavily_search_tool_function(query, url)

tavily_tool = Tool(
    name="Tavily Search",
    func=tavily_search_tool_function,
    description="Useful for searching the internet for recent information on Chemistry."
)

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def rag_search_tool_function(query: str) -> Union[Dict[str, Any], str]: # <--- MODIFIED NAME and added type hints
    rag_chain_local = get_rag_chain() # Assuming get_rag_chain() correctly fetches your RAG chain
    if rag_chain_local is None: return "RAG chain is not initialized."
    try: 
        return rag_chain_local.invoke({"query": query})
    except Exception as e: 
        logger.error(f"Error in RAG search for '{query}': {e}", exc_info=True)
        return f"Error performing RAG search: {str(e)}"

agent_llm_config = {
    "config_list": config_list,
    "timeout": 60,  # 建议值，您可以调整
    "temperature": 0.8, # 建议值
    "seed": 1234,        # 建议值
    "tools": [  # 使用正确的 "tools" 格式
        {
            "type": "function",
            "function": {
                "name": "rag_search_tool_function", # 确保与注册的函数名一致
                "description": "Search in the loaded chemical documents, experimental data, and literature using RAG. Use for specific, in-depth questions.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "The detailed query for document search."}},
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "tavily_search_tool_function", # 确保与注册的函数名一致
                "description": "Search the internet for up-to-date chemical information, news, or general knowledge using Tavily. Use for broad questions or recent information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The query for internet search."},
                        "url": {"type": "string", "description": "(Optional) A specific URL to focus the search on."}
                    },
                    "required": ["query"]
                }
            }
        },
        { # --- 新增：为 DataAnalystAgent.analyze_and_plot 定义工具 ---
            "type": "function",
            "function": {
                "name": "analyze_and_plot_data", # 这个名称将用于在 DataAnalystAgent 中注册
                "description": "Analyzes provided CSV data string and generates a specified plot (line, bar, histogram, scatter). Call this tool when data analysis or plotting is explicitly requested and CSV data is available or can be clearly inferred from the conversation history. If data is not clearly available, ask the user to provide it in CSV format before calling this tool.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data_str": {
                            "type": "string",
                            "description": "The CSV data as a string. Must include headers and be properly formatted CSV. Example: 'Header1,Header2\\nValue1A,Value1B\\nValue2A,Value2B'. Do NOT pass questions or placeholders like 'Please provide data' as this argument."
                        },
                        "plot_type": {
                            "type": "string",
                            "description": "Type of plot to generate. Supported types: 'line', 'bar', 'histogram', 'scatter'. Defaults to 'line' if not specified by the user.",
                            "enum": ["line", "bar", "histogram", "scatter"]
                        },
                        "x_col": {
                            "type": "string",
                            "description": "(Optional) Name of the column from data_str to use for the x-axis. If not provided, it will be inferred from the data."
                        },
                        "y_col": {
                            "type": "string",
                            "description": "(Optional) Name of the column from data_str to use for the y-axis. If not provided, it will be inferred from the data."
                        }
                    },
                    "required": ["data_str"] 
                }
            }
        }
    ]
}

manager_llm_config = {
    "config_list": config_list,
    "timeout": 60,
    "temperature": 0.8,
    "seed": 1234
}

def process_smiles(smiles):
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
            
        properties = {
            "formula": Chem.rdMolDescriptors.CalcMolFormula(mol),
            "molecular_weight": round(Descriptors.ExactMolWt(mol), 2),
            "num_atoms": mol.GetNumAtoms(),
            "num_bonds": mol.GetNumBonds(),
            "num_rings": rdMolDescriptors.CalcNumRings(mol),
            "charge": Chem.GetFormalCharge(mol),
            "logP": round(Descriptors.MolLogP(mol), 2),
            "TPSA": round(Descriptors.TPSA(mol), 2),
            "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol),
            "smiles": smiles
        }
        
        return properties
    except Exception as e:
        logger.error(f"Error processing SMILES: {str(e)}")
        return None

def process_smiles_for_3d(smiles):
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
            
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, randomSeed=42)
        AllChem.MMFFOptimizeMolecule(mol)
        
        conf = mol.GetConformer()
        
        structure = {
            "atoms": [
                {
                    "elem": atom.GetSymbol(),
                    "x": float(conf.GetAtomPosition(i).x),
                    "y": float(conf.GetAtomPosition(i).y),
                    "z": float(conf.GetAtomPosition(i).z)
                }
                for i, atom in enumerate(mol.GetAtoms())
            ],
            "bonds": [
                {
                    "start": bond.GetBeginAtomIdx(),
                    "end": bond.GetEndAtomIdx(),
                    "order": int(bond.GetBondTypeAsDouble())
                }
                for bond in mol.GetBonds()
            ]
        }
        
        return structure
    except Exception as e:
        logger.error(f"Error generating 3D structure: {str(e)}")
        return None

def mol_to_3d_json(mol):
    conf = mol.GetConformer()
    atoms = []
    for atom in mol.GetAtoms():
        pos = conf.GetAtomPosition(atom.GetIdx())
        atoms.append({
            "serial": atom.GetIdx() + 1,
            "elem": atom.GetSymbol(),
            "x": pos.x,
            "y": pos.y,
            "z": pos.z
        })
    
    bonds = []
    for bond in mol.GetBonds():
        bonds.append({
            "start": bond.GetBeginAtomIdx() + 1,
            "end": bond.GetEndAtomIdx() + 1,
            "order": int(bond.GetBondTypeAsDouble())
        })
    
    return {"atoms": atoms, "bonds": bonds}

def get_molecule_details(smiles):
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
            
        mol = Chem.AddHs(mol)
        AllChem.Compute2DCoords(mol)  # Use 2D coordinates instead of 3D
        
        # Basic molecular information
        info = {
            "formula": Chem.rdMolDescriptors.CalcMolFormula(mol),
            "molecular_weight": round(Descriptors.ExactMolWt(mol), 2),
            "num_atoms": mol.GetNumAtoms(),
            "num_bonds": mol.GetNumBonds(),
            "num_rings": Chem.rdMolDescriptors.CalcNumRings(mol),
            "charge": Chem.GetFormalCharge(mol),
            "logP": round(Descriptors.MolLogP(mol), 2),
            "TPSA": round(Descriptors.TPSA(mol), 2),
            "rotatable_bonds": Chem.rdMolDescriptors.CalcNumRotatableBonds(mol)
        }
        
        return info
        
    except Exception as e:
        logger.exception(f"Error getting molecule details: {smiles}")
        return None

def mol_to_3d_image(mol, size=(300, 300)):
    view = py3Dmol.view(width=size[0], height=size[1])
    view.addModel(Chem.MolToMolBlock(mol), "mol")
    view.setStyle({'stick':{}})
    view.zoomTo()
    png_data = view.png()
    buffered = io.BytesIO(base64.b64decode(png_data))
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

def visualize_smiles(smiles: str) -> str:
    try:
        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            return f"Invalid SMILES string: {smiles}"

        img = Draw.MolToImage(molecule)
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        return f"Error generating molecule image: {str(e)}"

def smiles_to_3d_mol(smiles):
    mol = Chem.MolFromSmiles(smiles)
    mol = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
    return mol

def mol_to_3d_image(mol, size=(300, 300)):
    view = py3Dmol.view(width=size[0], height=size[1])
    view.addModel(Chem.MolToMolBlock(mol), "mol")
    view.setStyle({'stick':{}})
    view.zoomTo()
    png_data = view.png()
    buffered = io.BytesIO(base64.b64decode(png_data))
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

class ThreadLocalStorage:
    """Thread-local storage for managing SMILES processing state"""
    def __init__(self):
        self.processed_smiles = set()
        
    def clear(self):
        self.processed_smiles.clear()

# Create a global thread-local storage instance
thread_local = ThreadLocalStorage()

class CustomUserProxyAgent(autogen.UserProxyAgent):
    """自定义UserProxyAgent，重写receive方法以修复工具调用消息格式"""
    
    def receive(self, message: Union[str, Dict[str, Any]], sender: Agent, request_reply: Optional[bool] = None, silent: bool = False) -> None:
        """处理接收到的消息，确保用户消息中的工具调用格式符合OpenAI API要求"""
        processed_message = message
        
        if isinstance(message, dict):
            processed_message = message.copy()
            
            if processed_message.get("role") == "user" and "tool_calls" in processed_message:
                if processed_message["tool_calls"] and isinstance(processed_message["tool_calls"], list):
                    tool_call_ids = [
                        tc.get("id") for tc in processed_message["tool_calls"] 
                        if isinstance(tc, dict) and "id" in tc
                    ]
                    if tool_call_ids:
                        processed_message["tool_call_id"] = tool_call_ids
                
                del processed_message["tool_calls"]
        
        super().receive(processed_message, sender, request_reply, silent)
    def preprocess_message_for_api(self, message: Union[str, Dict[str, Any]]) -> Union[str, Dict[str, Any]]:
        """Preprocess messages before sending to the API"""
        processed_message = message
        if isinstance(message, dict):
            processed_message = sanitize_message_for_api(message)
            
            # Additional checks for group chat context
            if processed_message.get("role") == "user" and processed_message.get("name"):
                # Some API implementations don't support 'name' for user
                if self._check_if_api_has_name_limitation():
                    # Save name for later if needed
                    self._last_user_name = processed_message.get("name")
                    del processed_message["name"]
        
        return processed_message
    
    def _check_if_api_has_name_limitation(self) -> bool:
        """检查当前使用的API是否有用户消息中name字段的限制"""
        # 获取配置中的API信息
        model = self.llm_config.get("config_list", [{}])[0].get("model", "").lower() if hasattr(self, "llm_config") else ""
        # 以下API提供商不支持用户消息中的name字段
        limited_providers = ["openai", "groq", "anthropic", "azure"]
        return any(provider in model or provider in str(self.llm_config) for provider in limited_providers)


def sanitize_message_for_api(message: Union[str, Dict[str, Any]]) -> Union[str, Dict[str, Any]]:
    """Thoroughly sanitize messages for OpenAI API compatibility"""
    if isinstance(message, str):
        return message
        
    if isinstance(message, dict):
        sanitized = message.copy()
        
        # Handle tool_calls in user messages
        if sanitized.get("role") == "user":
            if "tool_calls" in sanitized:
                # Extract tool_call_ids if available
                if sanitized["tool_calls"] and isinstance(sanitized["tool_calls"], list):
                    tool_call_ids = []
                    for tc in sanitized["tool_calls"]:
                        if isinstance(tc, dict) and "id" in tc:
                            tool_call_ids.append(tc["id"])
                    
                    # Only set tool_call_id if we have valid IDs
                    if tool_call_ids:
                        sanitized["tool_call_id"] = tool_call_ids
                
                # Always remove tool_calls from user messages
                del sanitized["tool_calls"]
        
        # Ensure assistant messages have properly formatted tool_calls
        elif sanitized.get("role") == "assistant":
            if "tool_calls" in sanitized and not isinstance(sanitized["tool_calls"], list):
                sanitized["tool_calls"] = []
            
            # Ensure content is always set (even if null)
            if "content" not in sanitized:
                sanitized["content"] = None
                
        return sanitized
    
    return message

def process_smiles_in_text(text: str) -> str:
    if not text:
        return text
    
    processor = get_global_smiles_processor()
    return processor.process_text(text)

def summarize_search_results(results, query):
    summary = f"Based on the search for '{query}', here are the key findings:\n\n"
    for i, result in enumerate(results, 1):
        summary += f"{i}. <a href='{result['url']}' target='_blank'>{result['title']}</a>\n"
        summary += f"   {result['content'][:200]}...\n\n"
    return summary

def process_search_results(search_results):
    """Process search results while maintaining SMILES deduplication"""
    if isinstance(search_results, str):
        try:
            search_results = json.loads(search_results)
        except json.JSONDecodeError:
            return [{"content": search_results, "url": "N/A", "title": "Search Result"}]
    processor = get_global_smiles_processor()
    
    # Process the search results while maintaining SMILES deduplication state
    if isinstance(search_results, list):
        return [{
            "content": process_smiles_in_text(result.get("content", "")),
            "url": result.get("url", "N/A"),
            "title": result.get("title", "Search Result")
        } for result in search_results]
    elif isinstance(search_results, dict):
        return [{
            "content": processor.process_text(search_results.get("content", "")),
            "url": search_results.get("url", "N/A"),
            "title": search_results.get("title", "Search Result")
        }]
    else:
        return [{"content": str(search_results), "url": "N/A", "title": "Search Result"}]

class PerformanceTest:
    def __init__(self, agents: List[Dict]):
        self.agents = agents
        self.performance_history = {agent['name']: [] for agent in agents}
    
    def evaluate_agent(self, agent: Dict) -> float:
        """
        Evaluate an agent's performance based on multiple factors.
        Returns a score between 0 and 1.
        """
        accuracy = random.uniform(0.5, 1.0)  # Simulated accuracy
        response_time = random.uniform(0.5, 2.0)  # Simulated response time in seconds
        task_completion = random.uniform(0.7, 1.0)  # Simulated task completion rate
        
        # Normalize response time (lower is better)
        normalized_time = 1 - (response_time - 0.5) / 1.5
        
        # Calculate weighted score
        score = (0.5 * accuracy + 0.3 * normalized_time + 0.2 * task_completion)
        return score
    
    def run_performance_test(self, num_iterations: int = 100):
        for _ in range(num_iterations):
            for agent in self.agents:
                score = self.evaluate_agent(agent)
                self.performance_history[agent['name']].append(score)
    
    def analyze_results(self):
        results = {}
        for agent_name, scores in self.performance_history.items():
            initial_performance = np.mean(scores[:10])  # Average of first 10 iterations
            final_performance = np.mean(scores[-10:])  # Average of last 10 iterations
            improvement_rate = stats.linregress(range(len(scores)), scores).slope
            
            # Find convergence point (when improvement rate slows significantly)
            convergence_point = next((i for i in range(10, len(scores)) 
                                      if abs(improvement_rate) < 0.001), len(scores))
            
            results[agent_name] = {
                "initial_performance": initial_performance,
                "final_performance": final_performance,
                "improvement_rate": improvement_rate,
                "convergence_point": convergence_point,
                "time_to_convergence": convergence_point  # Assuming 1 iteration = 1 time unit
            }
        
        return results

class ChemistryAgent(autogen.AssistantAgent):
    def __init__(self, name, *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.knowledge_base = set()
        self.skills = set()
        self.performance_history = []
        self.interaction_history = []
        self.evolution_level = 1
        self.performance_test = PerformanceTest([{"name": name, "evolutionLevel": 1}])
        self.smiles_processor = SmilesProcessor() 
    
    def generate_reply(self, messages=None, sender=None, **kwargs: Any) -> Union[str, Dict[str, Any], None]:
        # Handle the case when messages is None (called from group chat)
        if messages is None and sender is not None:
            # Get messages from chat history with this sender
            if hasattr(self, 'chat_messages') and sender in self.chat_messages:
                messages = self.chat_messages[sender]
            else:
                # No messages available, return a default response
                return {"role": "assistant", "name": self.name, 
                        "content": "I don't have enough context to provide a detailed response. Could you provide more information?", 
                        "tool_calls": []}
        
        llm_reply_obj = super().generate_reply(messages=messages, sender=sender, **kwargs)
        
        if isinstance(llm_reply_obj, dict):
            if llm_reply_obj.get("role") == "assistant":
                current_tool_calls = llm_reply_obj.get("tool_calls")
                if not isinstance(current_tool_calls, list): 
                    llm_reply_obj["tool_calls"] = []
                
                if "content" not in llm_reply_obj: 
                    llm_reply_obj["content"] = None 
            return llm_reply_obj
        elif isinstance(llm_reply_obj, str): 
            return {"role": "assistant", "name": self.name, "content": llm_reply_obj, "tool_calls": []}
        
        return llm_reply_obj
    
    def learn_from_feedback(self, feedback_analysis: Dict[str, Any]):
        agent_ratings = feedback_analysis['agent_ratings'].get(self.name, [])
        if agent_ratings:
            avg_rating = np.mean(agent_ratings)
            if avg_rating < 4.0:  
                topic_scores = {}
                for topic, ratings in feedback_analysis['topic_ratings'].items():
                    if len(ratings) > 0:
                        topic_scores[topic] = np.mean(ratings)
                weak_topics = [t for t, s in topic_scores.items() if s < 4.0]
                for topic in weak_topics:
                    self.strengthen_topic_knowledge(topic)
                    
    def strengthen_topic_knowledge(self, topic: str):
        new_skill = f"Advanced_{topic}"
        if new_skill not in self.skills:
            self.acquire_skill(new_skill)
        self.knowledge_base.add(f"Improved_{topic}_expertise")

    def learn(self, new_knowledge):
        self.knowledge_base.add(new_knowledge)
        logger.info(f"{self.name} learned: {new_knowledge}")

    def acquire_skill(self, new_skill):
        self.skills.add(new_skill)
        logger.info(f"{self.name} acquired new skill: {new_skill}")

    def evaluate_performance(self, feedback_score=None):
        if feedback_score is not None:
            # Use the provided feedback score
            score = self.feedback_to_score(feedback_score)
        else:
            # Use the existing performance test if no feedback is provided
            score = self.performance_test.evaluate_agent({"name": self.name, "evolutionLevel": self.evolution_level})
        
        self.performance_history.append(score)
        return score

    def feedback_to_score(self, feedback):
        if isinstance(feedback, (int, float)):
            return min(max(feedback, 0), 1)  # Ensure the score is between 0 and 1
        feedback_scores = {
            "excellent": 1.0,
            "good": 0.8,
            "average": 0.6,
            "poor": 0.4,
            "very poor": 0.2
        }
        return feedback_scores.get(feedback.lower(), 0.5) 

    def evolve(self):
        current_performance = self.evaluate_performance()
        if current_performance > 0.7 and self.evolution_level < 5:
            self.evolution_level += 1
            logger.info(f"{self.name} evolved to level {self.evolution_level}")
        elif current_performance < 0.5:
            self.refine_skills()

    def analyze_performance(self):
        if len(self.performance_history) > 10:
            results = self.performance_test.analyze_results()
            return results[self.name]
        return None

    def improve(self):
        common_topics = self.analyze_interactions()
        if common_topics:
            new_skill = f"Advanced_{random.choice(common_topics)}"
        else:
            # If no common topics, generate a generic improvement
            generic_topics = ["Research", "Analysis", "Safety", "Experimentation", "Documentation"]
            new_skill = f"Improved_{random.choice(generic_topics)}_Skills"
        
        self.acquire_skill(new_skill)
        logger.info(f"{self.name} evolved and gained a new skill: {new_skill}")

    def refine_skills(self):
        # Identify the least used skill and replace it
        if self.skills:
            least_used_skill = min(self.skills, key=lambda s: self.skill_usage_count(s))
            self.skills.remove(least_used_skill)
            new_skill = f"Refined_{least_used_skill}"
            self.acquire_skill(new_skill)
            logger.info(f"{self.name} refined skills: Removed {least_used_skill}, Added {new_skill}")

    def analyze_interactions(self):
        # Simple analysis of recent interactions to identify common topics
        topics = [interaction['topic'] for interaction in self.interaction_history[-10:] if 'topic' in interaction]
        return list(set(topics))  # Return unique topics

    def skill_usage_count(self, skill):
        # Count how many times a skill was used in recent interactions
        return sum(1 for interaction in self.interaction_history[-20:] if skill in interaction['skills_used'])

    def process_user_input(self, user_input, image_data=None):
        response = super().process_user_input(user_input)

        if image_data:
            llava_response = llava_call(user_input, image_data, llava_config_list[0])
            response = f"Image analysis: {llava_response}\n\n{response}"

        topic = self.extract_topic(user_input)
        skills_used = self.identify_skills_used(user_input, response)

        self.interaction_history.append({
            'user_input': user_input,
            'response': response,
            'topic': topic,
            'skills_used': skills_used
        })

        return response

    def extract_topic(self, text):
        keywords = ['reaction', 'compound', 'element', 'analysis', 'safety', 'experiment', 'procedure', 'equipment']
        for keyword in keywords:
            if keyword in text.lower():
                return keyword
        return 'general chemistry'  # Default topic if no keyword is found

    def identify_skills_used(self, user_input, response):
        # Identify skills used in the interaction (can be improved with more sophisticated analysis)
        skills_used = []
        for skill in self.skills:
            if skill.lower() in user_input.lower() or skill.lower() in response.lower():
                skills_used.append(skill)
        return skills_used

    def send(self, message: Union[str, Dict[str, Any]], recipient: Agent, request_reply: Optional[bool] = None, silent: bool = False) -> None:
        """
        Send a message to another agent after processing SMILES notation and sanitizing for API compatibility.
        
        Args:
            message: The message to send, either a string or a dict with a 'content' key
            recipient: The agent to send the message to
            request_reply: Whether to request a reply from the recipient
            silent: Whether to send the message silently
        """
        processed_message = message
        if isinstance(message, str): 
            processed_message = self.smiles_processor.process_text(message)
        elif isinstance(message, dict) and "content" in message and isinstance(message["content"], str):
            processed_message = message.copy()
            processed_message["content"] = self.smiles_processor.process_text(message["content"])
        
        # Apply message format normalization to ensure API compatibility
        processed_message = sanitize_message_for_api(processed_message)
        
        super().send(processed_message, recipient, request_reply, silent)

class DataAnalystAgent(ChemistryAgent):
    def __init__(self, name: str, llm_config: Dict[str, Any], system_message: Optional[str] = None, **kwargs: Any):
        super().__init__(name, llm_config=llm_config, 
                         system_message=system_message or "You are a data analyst. You are equipped with a tool called 'analyze_and_plot_data' that you can use to analyze CSV data and generate plots. When a user requests data analysis or a plot, and provides or references CSV data, you should use this tool. Ensure the 'data_str' argument for the tool contains actual CSV data, not questions or placeholders. If data is missing, ask the user to provide it clearly in CSV format before attempting to use the tool.", 
                         **kwargs)
        self.register_function(
            function_map={
                "analyze_and_plot_data": self.analyze_and_plot 
            }
        )

    def analyze_and_plot(self, data_str: str, plot_type: str = "line", x_col: Optional[str] = None, y_col: Optional[str] = None) -> Dict[str, Any]:
        logger.info(f"DataAnalystAgent.analyze_and_plot invoked. data_str (first 100): '{str(data_str)[:100]}...', plot_type: {plot_type}, x_col: {x_col}, y_col: {y_col}")
        plot_output = None
        analysis_summary = "Could not perform analysis."

        if not data_str or not isinstance(data_str, str) or len(data_str.strip()) == 0:
            analysis_summary = "Error: No data provided to analyze_and_plot_data tool (data_str is empty or invalid). Please ensure actual CSV data is passed to the 'data_str' argument."
            logger.warning(f"analyze_and_plot_data tool called with empty or invalid data_str.")
            return {"summary": analysis_summary, "plot_output": None, "plot_type": "none", "error": "No data provided to tool"}

        placeholder_keywords = ["please provide", "what type of plot", "csv data as a string", "enter your data"]
        data_str_lower = data_str.lower()
        if any(keyword in data_str_lower for keyword in placeholder_keywords) and not (',' in data_str and '\n' in data_str): 
            analysis_summary = f"Error: The 'data_str' argument received by analyze_and_plot_data tool seems to be a question or placeholder text ('{data_str[:100]}...'), not actual CSV data. The tool requires valid CSV data for analysis."
            logger.warning(f"analyze_and_plot_data tool called with potential placeholder text as data_str: {data_str[:100]}")
            return {"summary": analysis_summary, "plot_output": None, "plot_type": "none", "error": "Invalid data format passed to tool; expected CSV data."}

        try:
            data_io = io.StringIO(data_str)
            df = pd.read_csv(data_io)
            if df.empty: 
                analysis_summary = "The provided CSV data is empty after parsing."
                return {"summary": analysis_summary, "plot_output": None, "plot_type": "none", "error": "Parsed CSV data is empty"}
            
            analysis_summary = f"Data Overview:\n{df.head().to_string()}\n\nDescriptive Statistics:\n{df.describe(include='all').to_string()}\n"
            numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
            
            if not numeric_cols: 
                analysis_summary += "\nNo numeric columns found in the data for plotting."
                return {"summary": analysis_summary, "plot_output": None, "plot_type": "none", "error": "No numeric columns for plotting"}

            original_x_col, original_y_col = x_col, y_col 
            if x_col is None and plot_type != "histogram":
                if len(df.columns) > 0:
                    x_col = df.columns[0]
            if y_col is None:
                if len(numeric_cols) > 0:
                    y_col = numeric_cols[0]
                elif len(df.columns) > 1 and plot_type != "histogram":
                    y_col = df.columns[1]
                elif len(df.columns) > 0:
                    y_col = df.columns[0]
            
            if plot_type == "histogram" and original_x_col and not original_y_col: 
                y_col = original_x_col
                x_col = None 

            plot_generated = False
            error_msg = None
            if plot_type != "histogram":
                if not x_col or x_col not in df.columns:
                    error_msg = f"X-column '{x_col}' not found or not specified for plot type '{plot_type}'."
                elif not y_col or y_col not in df.columns:
                    error_msg = f"Y-column '{y_col}' not found or not specified for plot type '{plot_type}'."
            elif not y_col or y_col not in df.columns: 
                error_msg = f"Column '{y_col}' for histogram not found or not specified."
             
            if error_msg:
                analysis_summary += f"\nError: {error_msg}"
                return {"summary": analysis_summary, "plot_output": None, "plot_type": "none", "error": error_msg}

            plt.figure(figsize=(10, 6))
            sns.set_theme(style="whitegrid")
            title_str, summary_add = "", ""

            if plot_type == "line": 
                sns.lineplot(x=df[x_col], y=df[y_col], marker='o')
                title_str = f"Line Plot of {y_col} vs {x_col}"
                summary_add = f"\nGenerated line plot: {y_col} vs {x_col}."
                plot_generated = True
            elif plot_type == "bar":
                if pd.api.types.is_numeric_dtype(df[y_col]):
                    sns.barplot(x=df[x_col], y=df[y_col], palette="viridis")
                    title_str = f"Bar Plot of {y_col} by {x_col}"
                    summary_add = f"\nGenerated bar plot: {y_col} by {x_col}."
                    plot_generated = True
                else:
                    analysis_summary += f"\nError: Y-column '{y_col}' must be numeric for a bar plot."
                    error_msg = f"Y-column '{y_col}' not numeric for bar plot"
            elif plot_type == "histogram":
                if pd.api.types.is_numeric_dtype(df[y_col]): 
                    sns.histplot(df[y_col], kde=True, color="skyblue", bins=min(30, df[y_col].nunique()))
                    title_str = f"Histogram of {y_col}"
                    summary_add = f"\nGenerated histogram for {y_col}."
                    plot_generated = True
                else:
                    analysis_summary += f"\nError: Column '{y_col}' must be numeric for a histogram."
                    error_msg = f"Column '{y_col}' not numeric for histogram"
            elif plot_type == "scatter": 
                hue_col = df.columns[2] if len(df.columns) > 2 and df.columns[2] not in [x_col, y_col] else None
                sns.scatterplot(x=df[x_col], y=df[y_col], hue=hue_col, palette="deep", s=100)
                title_str = f"Scatter Plot of {y_col} vs {x_col}"
                summary_add = f"\nGenerated scatter plot: {y_col} vs {x_col}."
                plot_generated = True
            else: 
                analysis_summary += f"\nError: Unsupported plot type '{plot_type}' requested."
                error_msg = f"Unsupported plot type '{plot_type}'"

            if plot_generated:
                plt.title(title_str, fontsize=16)
                analysis_summary += summary_add
                plt.xlabel(str(x_col if plot_type != "histogram" else y_col), fontsize=12)
                plt.ylabel(str(y_col if plot_type != "histogram" else "Frequency"), fontsize=12)
                plt.xticks(rotation=45, ha='right')
                plt.tight_layout()
                img_io = io.BytesIO()
                plt.savefig(img_io, format='png', bbox_inches='tight')
                plt.close()
                plot_output = {"type": "base64_image", "data": base64.b64encode(img_io.getvalue()).decode('utf-8'), "format": "png"}
            else:
                return {
                    "summary": analysis_summary,
                    "plot_output": None,
                    "plot_type": "none",
                    "error": error_msg or "Plot generation failed due to unspecified error."
                }

        except pd.errors.ParserError as pe:
            analysis_summary = f"Error: Could not parse the provided data_str as CSV. Please check the format. Details: {str(pe)}"
            logger.error(f"Pandas ParserError for data_str: {str(pe)}", exc_info=True)
            return {"summary": analysis_summary, "plot_output": None, "plot_type": "none", "error": f"CSV Parsing Error: {str(pe)}"}
        except pd.errors.EmptyDataError: 
            analysis_summary = "Error: The provided data string was empty or not valid CSV after attempting to parse."
            return {"summary": analysis_summary, "plot_output": None, "plot_type": "none", "error": "Empty or invalid CSV data"}
        except KeyError as ke: 
            column_list = list(df.columns) if 'df' in locals() else 'unknown'
            analysis_summary = f"Error: Column not found in data - {str(ke)}. Available columns: {column_list}"
            logger.error(f"Plotting KeyError: {ke}", exc_info=True)
            return {"summary": analysis_summary, "plot_output": None, "plot_type": "none", "error": f"Column not found: {str(ke)}"}
        except ValueError as ve: 
            analysis_summary = f"Plotting error: {ve}. Ensure columns suit plot type."
            logger.error(f"Plotting ValueError: {ve}", exc_info=True)
            return {"summary": analysis_summary, "plot_output": None, "plot_type": "none", "error": f"Plotting ValueError: {str(ve)}"}
        except Exception as e: 
            logger.error(f"DataAnalystAgent error in analyze_and_plot: {e}", exc_info=True)
            analysis_summary = f"An unexpected error occurred during analysis/plotting: {e}"
            return {"summary": analysis_summary, "plot_output": None, "plot_type": "none", "error": f"Unexpected error: {str(e)}"}
        
        return_dict = {"summary": analysis_summary, "plot_output": plot_output, "plot_type": plot_type if plot_output else "none"}
        if not plot_output and not ("error" in return_dict and return_dict["error"]):
            return_dict["error"] = analysis_summary 
        return return_dict

    def generate_reply(self, messages=None, sender=None, **kwargs):
        # Handle the case when messages is None (called from group chat)
        if messages is None and sender is not None:
            # Get messages from chat history with this sender
            if hasattr(self, 'chat_messages') and sender in self.chat_messages:
                messages = self.chat_messages[sender]
            else:
                # No messages available, return a default response
                return {"role": "assistant", "name": self.name, 
                        "content": "I need data to analyze. Please provide CSV data in this format:\n\n```csv\nheader1,header2\nvalue1,value2\nvalue3,value4\n```", 
                        "tool_calls": []}
        
        # Now proceed with the original implementation
        if messages:
            last_message = messages[-1]
            content = last_message.get("content", "")
            trigger_phrases = ["analyze data", "plot data", "generate plot", "create chart for data"]
            triggered = any(phrase in content.lower() for phrase in trigger_phrases)

            if triggered:
                logger.info(f"{self.name} triggered for data analysis by: '{content[:100]}...'")
                
                data_str_match = re.search(r"data:\s*```csv\s*([\s\S]+?)\s*```", content, re.IGNORECASE)
                if not data_str_match: 
                     data_str_match = re.search(r"data:\s*([\s\S]+?)(?=\s*(?:and plot|and analyze|generate plot|$))", content, re.IGNORECASE)

                plot_type_match = re.search(r"plot an? (line|bar|histogram|scatter)\s*(?:chart|plot)", content, re.IGNORECASE)
                x_col_match = re.search(r"(?:x-axis|x column|x_col)\s*(?:as|is|=)\s*([\w.-]+)", content, re.IGNORECASE)
                y_col_match = re.search(r"(?:y-axis|y column|y_col)\s*(?:as|is|=)\s*([\w.-]+)", content, re.IGNORECASE)

                data_to_analyze = data_str_match.group(1).strip() if data_str_match else ""
                if not data_to_analyze:
                    for i in range(len(messages) - 2, -1, -1):
                        prev_content = messages[i].get("content", "")
                        prev_data_match = re.search(r"data:\s*```csv\s*([\s\S]+?)\s*```", prev_content, re.IGNORECASE)
                        if prev_data_match:
                            data_to_analyze = prev_data_match.group(1).strip()
                            logger.info(f"Found data in previous message for {self.name}.")
                            break
                
                plot_type_req = plot_type_match.group(1).lower() if plot_type_match else "line"
                x_col_req = x_col_match.group(1) if x_col_match else None
                y_col_req = y_col_match.group(1) if y_col_match else None
                
                logger.info(f"Analysis request for {self.name}: data_present={bool(data_to_analyze)}, plot_type='{plot_type_req}', x='{x_col_req}', y='{y_col_req}'")

                if not data_to_analyze:
                    missing_data_msg = ("I can help with data analysis and plotting, but I need the data first. "
                                        "Please provide the data in a CSV format, like this:\n"
                                        "`data: ```csv\nheader1,header2\nvalue1,value2\nvalue3,value4\n```\n"
                                        "What data would you like me to analyze?")
                    return {"role": "assistant", "name": self.name, "content": missing_data_msg, "tool_calls": []}

                analysis_result = self.analyze_and_plot(data_to_analyze, plot_type=plot_type_req, x_col=x_col_req, y_col=y_col_req)
                
                response_content = analysis_result["summary"]
                final_response = {
                    "role": "assistant", 
                    "name": self.name,
                    "content": response_content,
                    "tool_calls": []  
                }
                if analysis_result.get("plot_output"): 
                    final_response["plot_output"] = analysis_result["plot_output"]
                    logger.info(f"Plot generated by {self.name}. Type: {analysis_result.get('plot_type')}")
                else:
                    logger.info(f"{self.name} completed analysis but no plot was generated. Reason/Type: {analysis_result.get('plot_type')}")
                
                return final_response

        llm_reply_obj = super().generate_reply(messages=messages, sender=sender, **kwargs)
        
        if isinstance(llm_reply_obj, str):
            return {"role": "assistant", "name": self.name, "content": llm_reply_obj, "tool_calls": []}
        elif isinstance(llm_reply_obj, dict):
            llm_reply_obj.setdefault("role", "assistant") 
            llm_reply_obj.setdefault("name", self.name)   
            if "tool_calls" not in llm_reply_obj and not llm_reply_obj.get("function_call"):
                if llm_reply_obj.get("content"):
                    llm_reply_obj["tool_calls"] = []
                elif not llm_reply_obj.get("tool_calls"):
                    llm_reply_obj["tool_calls"] = []
            return llm_reply_obj
            
        return llm_reply_obj

class ChemistryLab:
    def __init__(self, literature_path=""):
        self.agents = []
        self.groupchat = None
        self.manager = None
        self.literature_path = literature_path
        self.setup_agents()
        self.load_documents()
        self.llm = ChatOpenAI(model_name="llama3-70b-8192", openai_api_key=config_list[1]["api_key"], openai_api_base=config_list[1]["base_url"])
        self.performance_history = []
        self.smiles_processor = get_global_smiles_processor()
    
        if hasattr(self, 'db') and self.db is not None:
            self.rag_chain = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type="stuff",
                retriever=self.db.as_retriever(search_kwargs={"k": 3})
            )
        else:
            self.rag_chain = None

    def extract_topic(self, text: str) -> str:

        topic_keywords = {
            'organic_chemistry': ['organic', 'synthesis', 'reaction', 'compound', 'molecule'],
            'inorganic_chemistry': ['inorganic', 'metal', 'crystal', 'coordination'],
            'analytical_chemistry': ['analysis', 'measurement', 'concentration', 'spectrum'],
            'physical_chemistry': ['thermodynamics', 'kinetics', 'equilibrium', 'energy'],
            'safety': ['safety', 'hazard', 'protection', 'precaution', 'risk'],
            'lab_management': ['equipment', 'procedure', 'protocol', 'setup']
        }
        
        text = text.lower()
        
        topic_matches = {
            topic: sum(1 for keyword in keywords if keyword in text)
            for topic, keywords in topic_keywords.items()
        }
        
        if any(topic_matches.values()):
            return max(topic_matches.items(), key=lambda x: x[1])[0]
            
        return 'general'
        
    def integrate_feedback(self):
        feedback_analysis = self.chat_storage.analyze_feedback_trends()
        for agent in self.agents:
            agent.learn_from_feedback(feedback_analysis)
        self.update_response_strategy(feedback_analysis)
    
    def update_response_strategy(self, feedback_analysis: Dict[str, Any]):
        best_agents = {}
        for agent, ratings in feedback_analysis['agent_ratings'].items():
            if len(ratings) > 0:
                avg_rating = np.mean(ratings)
                best_agents[agent] = avg_rating
                
        topic_specialists = {}
        for topic, ratings in feedback_analysis['topic_ratings'].items():
            best_agent = max(best_agents.items(), key=lambda x: x[1])[0]
            topic_specialists[topic] = best_agent
            
        self.topic_specialists = topic_specialists

    def rag_search(self, query: str) -> str:
        if self.rag_chain is None:
            return "RAG search is not available - no documents loaded"
        try:
            return self.rag_chain.invoke({"query": query})
        except Exception as e:
            logger.error(f"Error in RAG search: {str(e)}")
            return f"Error performing RAG search: {str(e)}"

    def recognize_intent(self, query: str) -> str:
        prompt = f"""Analyze the following query and determine the most appropriate search strategy:
        Query: {query}

        Possible intents:
        1. Requires real-time updated information (use Tavily search)
        2. Requires deep information or complex queries in technical, academic, or research fields (use RAG search)
        3. Requires both real-time and in-depth information (use both Tavily and RAG search)
        4. Can be answered with existing knowledge (no search required)

        Respond with only the number of the most appropriate intent."""

        response = self.llm.predict(prompt)
        return response.strip()

    def process_user_input(self, user_input: str, image_data: Union[bytes, None] = None, literature_path: str = None, web_url_path: str = None) -> List[Dict[str, Any]]:
        self.integrate_feedback()
        topic = self.extract_topic(user_input)
        
        if "analyze data" in user_input.lower() or "plot" in user_input.lower():
            primary_agent = next((agent for agent in self.agents if agent.name == "Data_Analyst"), self.agents[0])
        elif hasattr(self, 'topic_specialists') and self.topic_specialists and topic in self.topic_specialists:
            primary_agent = next((agent for agent in self.agents if agent.name == self.topic_specialists[topic]), self.agents[0])
        else:
            primary_agent = self.agents[0]

        logger.info(f"Selected primary agent: {primary_agent.name} for topic/task: {topic}")
        
        if literature_path and literature_path != self.literature_path:
            logger.info(f"New literature path detected. Updating from {self.literature_path} to {literature_path}")
            self.literature_path = literature_path
            self.load_documents()

        logger.info(f"Processing user input: {user_input}")
        logger.info(f"Web URL Path: {web_url_path}")

        if not self.groupchat or not self.manager:
            self.setup_groupchat()

        try:
            if image_data:
                llava_response = llava_call(user_input, image_data, llava_config_list[0])
                user_input = f"{user_input}\n[IMAGE_ANALYSIS:{llava_response}]"
                
            intent = self.recognize_intent(user_input)
            logger.info(f"Recognized intent: {intent}")

            search_results = ""
            if intent == "1":
                search_results = tavily_search(user_input, url=web_url_path if web_url_path and is_valid_url(web_url_path) else None)
                search_results = f"[TAVILY_SEARCH:{search_results}]"
            elif intent == "2":
                search_results = rag_search(user_input)
                search_results = f"[RAG_SEARCH:{search_results}]"
            elif intent == "3":
                tavily_results = tavily_search(user_input, url=web_url_path if web_url_path and is_valid_url(web_url_path) else None)
                rag_results = rag_search(user_input)
                search_results = f"[TAVILY_SEARCH:{tavily_results}]\n[RAG_SEARCH:{rag_results}]"

            if search_results:
                user_input = f"{user_input}\n{search_results}"
                
            chat_result = self.manager.initiate_chat(
                primary_agent, 
                message=user_input,
            )

            chat_history = chat_result.chat_history if hasattr(chat_result, 'chat_history') else chat_result

            processed_messages = []
            for message in chat_history:
                if isinstance(message, dict) and 'role' in message:
                    processed_content = message['content']
                    if message['role'] == 'assistant':
                        processed_content = process_smiles_in_text(processed_content)
                    
                    processed_messages.append({
                        'role': message['role'],
                        'name': message.get('name', 'AI Assistant') if message['role'] == 'assistant' else 'You',
                        'content': processed_content
                    })

            for agent in self.agents:
                agent.evolve()
                
            return processed_messages

        except Exception as e:
            logger.error(f"Error in process_user_input: {str(e)}", exc_info=True)
            return [{
                'role': 'assistant',
                'name': 'System',
                'content': f"Error processing your input: {str(e)}"
            }]
        
    def load_documents(self):
        logger.info(f"Loading documents. Literature path: {self.literature_path}")

        # Load experiment data
        experiment_data = load_documents("E://HuaweiMoveData//Users//makangyong//Desktop//output.txt")
        logger.info(f"Loaded {len(experiment_data)} experiment documents")

        # Load literature (if available)
        literature = []
        if self.literature_path:
            if os.path.exists(self.literature_path):
                literature = load_documents(self.literature_path)
                logger.info(f"Loaded {len(literature)} literature documents from {self.literature_path}")
            else:
                logger.warning(f"Literature path does not exist: {self.literature_path}")

        # Combine all documents
        all_documents = experiment_data + literature
        logger.info(f"Total documents loaded: {len(all_documents)}")

        # Check if we have any documents before proceeding
        if not all_documents:
            logger.warning("No documents loaded. Skipping embedding and vector store creation.")
            self.db = None
        else:
            try:
                text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
                texts = text_splitter.split_documents(all_documents)
                logger.info(f"Split documents into {len(texts)} chunks")

                embeddings = HuggingFaceEmbeddings()
                self.db = Chroma.from_documents(texts, embeddings)
                logger.info("Successfully created Chroma vector store")
            except Exception as e:
                logger.error(f"Error creating vector store: {str(e)}", exc_info=True)
                self.db = None

    def process_user_input(self, user_input, image_data=None, literature_path=None, web_url_path=None):
        if literature_path and literature_path != self.literature_path:
            logger.info(f"New literature path detected. Updating from {self.literature_path} to {literature_path}")
            self.literature_path = literature_path
            self.load_documents()  # Reload documents when literature_path changes

        logger.info(f"Processing user input: {user_input}")
        logger.info(f"Web URL Path: {web_url_path}")

        if not self.groupchat or not self.manager:
            self.setup_groupchat()

        try:
            if image_data:
                llava_response = llava_call(user_input, image_data, llava_config_list[0])
                user_input = f"{user_input}\n[IMAGE_ANALYSIS:{llava_response}]"

            # Check if a valid URL is provided
            if web_url_path and is_valid_url(web_url_path):
                search_result = tavily_search(user_input, url=web_url_path)
            else:
                search_result = tavily_search(user_input)

            if search_result:
                processed_results = process_search_results(search_result)
                summary = summarize_search_results(processed_results, user_input)
                user_input = f"{user_input}\n[WEB_SEARCH_SUMMARY:{summary}]"

            chat_result = self.manager.initiate_chat(
                self.agents[0],
                message=user_input,
            )

            chat_history = chat_result.chat_history if hasattr(chat_result, 'chat_history') else chat_result

            processed_messages = []
            for message in chat_history:
                logger.info(f"Processing message: {message}")
                if isinstance(message, dict) and 'role' in message:
                    if message['role'] == 'human':
                        processed_messages.append({
                            'role': 'user',
                            'name': 'You',
                            'content': message['content']
                        })
                    elif message['role'] == 'assistant':
                        agent_name = message.get('name', 'AI Assistant')
                        processed_content = process_smiles_in_text(message['content'])
                        msg_to_send = {
                            'role': 'assistant',
                            'name': agent_name,
                            'content': processed_content
                       }
            
                        # If message has plot_output, include it
                        if 'plot_output' in message:
                            msg_to_send['plot_output'] = message['plot_output']
                
                        processed_messages.append(msg_to_send)

            for msg in processed_messages:  
                if isinstance(msg, dict) and 'content' in msg:
                    msg['content'] = self.smiles_processor.process_text(msg['content'])
            
            for agent in self.agents:
                agent.evolve()

            logger.info(f"Generated responses: {json.dumps(processed_messages, indent=2)}")
            return processed_messages
        except Exception as e:
            logger.error(f"Error processing user input: {str(e)}", exc_info=True)
            return [{
                'role': 'assistant',
                'name': 'System',
                'content': f"Error processing your input: {str(e)}"
            }]

    def get_user_feedback(self, feedback_data):
        logger.info(f"Processing feedback: {feedback_data}")
        try:
            for agent_name, score in feedback_data.items():
                agent = next((a for a in self.agents if a.name == agent_name), None)
                if agent:
                    performance_score = agent.evaluate_performance(score)
                    logger.info(f"Applied feedback to {agent_name}: {score}, resulting performance: {performance_score}")
                else:
                    logger.warning(f"Agent {agent_name} not found")
        except Exception as e:
            logger.error(f"Error processing feedback: {str(e)}", exc_info=True)
            raise

    def simulate(self, num_rounds):
        for round in range(num_rounds):
            for agent in self.agents:
                performance = agent.evaluate_performance()
                self.performance_history.append((agent.name, round, performance))
                agent.evolve()

            # Perform knowledge sharing after each round
            self.knowledge_sharing()

            if round % 10 == 0:  # Analyze every 10 rounds
                self.analyze_system_performance()

    def knowledge_sharing(self):
        for agent in self.agents:
            other_agents = [a for a in self.agents if a != agent]
            if other_agents:
                sharing_partner = random.choice(other_agents)
                shared_knowledge = random.choice(list(agent.knowledge_base)) if agent.knowledge_base else None
                if shared_knowledge:
                    sharing_partner.learn(shared_knowledge)
                    logger.info(f"{agent.name} shared knowledge '{shared_knowledge}' with {sharing_partner.name}")

    def analyze_system_performance(self):
        performance_data = {}
        for agent in self.agents:
            analysis = agent.analyze_performance()
            if analysis:
                agent_data = {
                    "evolution_level": agent.evolution_level,
                    "initial_performance": analysis['initial_performance'],
                    "current_performance": analysis['final_performance'],
                    "improvement_rate": analysis['improvement_rate'],
                    "knowledge_base_size": len(agent.knowledge_base)  # Add this line to track knowledge base size
                }
                
                convergence_point = detect_convergence(agent.performance_history)
                if convergence_point != -1:
                    agent_data["convergence_point"] = convergence_point
                    agent_data["time_to_convergence"] = convergence_point
                else:
                    agent_data["convergence_point"] = None

                performance_data[agent.name] = agent_data

                logger.info(f"Performance analysis for {agent.name}:")
                logger.info(f"  Current Evolution Level: {agent.evolution_level}")
                logger.info(f"  Initial Performance: {analysis['initial_performance']:.4f}")
                logger.info(f"  Current Performance: {analysis['final_performance']:.4f}")
                logger.info(f"  Improvement Rate: {analysis['improvement_rate']:.4f}")
                logger.info(f"  Knowledge Base Size: {len(agent.knowledge_base)}")
                
                if convergence_point != -1:
                    logger.info(f"  Convergence Detected at Iteration: {convergence_point}")
                    logger.info(f"  Time to Convergence: {convergence_point} iterations")
                else:
                    logger.info("  Convergence Not Yet Detected")

        # System-wide analysis
        all_performances = [perf for _, _, perf in self.performance_history]
        system_improvement_rate = np.polyfit(range(len(all_performances)), all_performances, 1)[0]
        logger.info(f"System-wide Improvement Rate: {system_improvement_rate:.4f}")
        
        system_convergence = detect_convergence(all_performances)
        if system_convergence != -1:
            logger.info(f"System-wide Convergence Detected at Iteration: {system_convergence}")
            logger.info(f"Time to System Convergence: {system_convergence} iterations")
        else:
            logger.info("System-wide Convergence Not Yet Detected")

        performance_data["system"] = {
            "improvement_rate": system_improvement_rate,
            "convergence_point": system_convergence,
            "time_to_convergence": system_convergence if system_convergence != -1 else None,
            "total_knowledge_base_size": sum(len(agent.knowledge_base) for agent in self.agents)  # Add this line to track total knowledge
        }

        return performance_data
        
    def setup_agents(self):
        self.agents = [] 
        agent_definitions = [ 
            ("Lab_Director", "You are the director of a chemistry laboratory. Your role is to oversee research, assign tasks, and ask for summaries or specific analyses. If data is mentioned or a chart is needed, you can request the Data_Analyst to perform the task using its 'analyze_and_plot_data' tool. Be specific about the data source (e.g., 'use the data provided by the user' or 'use data from message X') and the desired plot type."),
            ("Senior_Chemist", "You are a senior chemist with expertise in organic, inorganic, and physical chemistry. Provide detailed answers and insights on complex chemical processes. If data analysis is needed, suggest the Lab_Director to ask the Data_Analyst."),
            ("Lab_Manager", "You are a laboratory manager responsible for overseeing chemical experiments, ensuring safety protocols, and managing resources. Plan and design projects with efficiency and safety in mind."),
            ("Safety_Officer", "You are a chemical safety officer responsible for reviewing experimental procedures and ensuring compliance with safety regulations. Provide feedback on safety measures and potential hazards."),
            ("Analytical_Chemist", "You are an analytical chemist specializing in chemical analysis techniques and instrumentation. Provide expertise on analytical methods, data interpretation, and quality control.")
        ]

        for name, sys_msg in agent_definitions: 
            agent = ChemistryAgent(name=name, system_message=sys_msg, llm_config=agent_llm_config)
            agent.register_function(function_map={
                "rag_search_tool_function": rag_search_tool_function, 
                "tavily_search_tool_function": tavily_search_tool_function
            })
            self.agents.append(agent)
    
        data_analyst_system_message = (
            "You are a data analyst. You are equipped with a tool called 'analyze_and_plot_data' "
            "that you can use to analyze CSV data and generate plots. "
            "When a user requests data analysis or a plot, and provides or references CSV data, "
            "you should use this tool. Ensure the 'data_str' argument for the tool contains actual CSV data, "
            "not questions or placeholders. If data is missing, clearly state what data is needed in CSV format "
            "before suggesting the user provide it or before you attempt to call the tool again. "
            "If you call the tool, present the 'summary' from the tool's result to the user. "
            "If the tool also provides 'plot_output', it will be displayed automatically."
        )
        data_analyst = DataAnalystAgent(
            name="Data_Analyst", 
            llm_config=agent_llm_config, # 使用包含所有工具定义的 agent_llm_config
            system_message=data_analyst_system_message
        )
        self.agents.append(data_analyst)
        logger.info(f"Initialized agents: {[a.name for a in self.agents]}")

    def setup_groupchat(self):
        self.user_proxy = CustomUserProxyAgent(  # 使用我们的自定义类
            name="User_Proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=10,
            is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
            code_execution_config=False,
            default_auto_reply="Please continue or summarize.",
            system_message="You are a user proxy. Relay user messages to the group and return the final response."
        )

        self.groupchat = autogen.GroupChat(
            agents=[self.user_proxy] + self.agents,
            messages=[],
            max_round=12,
            speaker_selection_method="auto",
            allow_repeat_speaker=False,
        )
        self.manager = autogen.GroupChatManager(
            groupchat=self.groupchat, 
            llm_config=manager_llm_config
        )
        logger.info("Group chat and manager set up successfully.")

def get_chemistry_lab(literature_path=""):
    return ChemistryLab(literature_path)

# Keep the simulate function at the end
def simulate(message, image_data=None):
    chemistry_lab = get_chemistry_lab()
    return chemistry_lab.process_user_input(message, image_data)

def detect_convergence(performance_history, window_size=20, threshold=0.001):
    """
    Detect convergence in performance history.
    
    Args:
    performance_history (list): List of performance scores over time.
    window_size (int): Size of the sliding window for slope calculation.
    threshold (float): Threshold for considering the slope as converged.
    
    Returns:
    int: Index at which convergence is detected, or -1 if not converged.
    """
    if len(performance_history) < window_size * 2:
        return -1  # Not enough data to determine convergence
    
    for i in range(window_size, len(performance_history) - window_size):
        window = performance_history[i-window_size:i+window_size]
        slope, _, _, _, _ = stats.linregress(range(len(window)), window)
        
        if abs(slope) < threshold:
            return i
    
    return -1  # Convergence not detected