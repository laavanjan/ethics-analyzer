import ast
import re
from collections import defaultdict
from typing import Dict, List, Any
from dataclasses import dataclass
import github  # For type hints

@dataclass
class EthicsIssue:
    file_path: str
    line_number: int
    issue_type: str
    severity: str
    message: str
    suggestion: str
    code_snippet: str

class EthicsAnalyzer:
    def __init__(self):
        self.biased_terms = {
            'bias': ['blacklist', 'whitelist', 'master', 'slave', 'cripple', 'dummy', 'sanitize'],
            'gender': ['he', 'she', 'man', 'woman', 'male', 'female', 'boy', 'girl', 'guys'],
            'race': ['white', 'black', 'asian', 'indian', 'native', 'colored'],
            'ability': ['blind', 'deaf', 'mute', 'retard', 'insane', 'crazy']
        }
        
        self.privacy_patterns = [
            r'(password|pwd|pass)\s*[=:]\s*["\'][^"\']*["\']',
            r'(api[_-]?key|secret|token)\s*[=:]\s*["\'][^"\']*["\']',
            r'password\s*=\s*["\'][^"\']+["\']',
            r'{"password"',
            r'"password"\s*:',
        ]
        
        self.issues = []
    
    def analyze_file(self, file_path: str, content: str) -> List[EthicsIssue]:
        file_issues = []
        
        # AST analysis (robust)
        try:
            tree = ast.parse(content)
            file_issues.extend(self._analyze_ast(tree, file_path))
        except SyntaxError as e:
            print(f"⚠️  Syntax error in {file_path}: {e}")
        
        # Text analysis
        file_issues.extend(self._analyze_text(content, file_path))
        
        self.issues.extend(file_issues)
        return file_issues
    
    def _analyze_ast(self, tree: ast.AST, file_path: str) -> List[EthicsIssue]:
        issues = []
        
        for node in ast.walk(tree):
            node_lineno = getattr(node, 'lineno', 1)
            
            # Names: variables, functions, classes
            name_nodes = [
                (node, getattr(node, 'id', getattr(node, 'name', ''))) 
                for node in [node] if isinstance(node, (ast.Name, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
            ]
            
            for node_obj, name in name_nodes:
                if name:
                    issues.extend(self._check_naming_bias(name, getattr(node_obj, 'lineno', node_lineno), file_path))
            
            # String constants
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                issues.extend(self._check_string_bias(node.value, node_lineno, file_path))
        
        return issues
    
    def _analyze_text(self, content: str, file_path: str) -> List[EthicsIssue]:
        issues = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            # Privacy patterns
            for pattern in self.privacy_patterns:
                if re.search(pattern, line, re.IGNORECASE | re.MULTILINE):
                    issues.append(EthicsIssue(
                        file_path=file_path, line_number=i, issue_type='privacy',
                        severity='critical', message='Potential hardcoded credential',
                        suggestion='Use environment variables (os.getenv())',
                        code_snippet=line.strip()
                    ))
            
            # Comments
            if line.strip().startswith('#'):
                issues.extend(self._check_string_bias(line, i, file_path))
        
        return issues
    
    def _check_naming_bias(self, name: str, line: int, file_path: str) -> List[EthicsIssue]:
        issues = []
        name_lower = name.lower()
        
        for issue_type, terms in self.biased_terms.items():
            for term in terms:
                if term in name_lower:
                    issues.append(EthicsIssue(
                        file_path=file_path, line_number=line, issue_type=issue_type,
                        severity='medium', message=f'Biased identifier: "{name}"',
                        suggestion=f'Avoid "{term}" - use neutral alternatives',
                        code_snippet=name
                    ))
        return issues
    
    def _check_string_bias(self, text: str, line: int, file_path: str) -> List[EthicsIssue]:
        issues = []
        text_lower = text.lower()
        
        for issue_type, terms in self.biased_terms.items():
            for term in terms:
                if term in text_lower:
                    issues.append(EthicsIssue(
                        file_path=file_path, line_number=line, issue_type=issue_type,
                        severity='low', message=f'Biased language: "{term}"',
                        suggestion='Use inclusive language',
                        code_snippet=text[:80] + '...' if len(text) > 80 else text
                    ))
        
        return issues[:2]  # Limit per string to avoid spam
    
    def generate_report(self) -> Dict[str, Any]:
        by_type = defaultdict(int)
        severity_counts = defaultdict(int)
        
        for issue in self.issues:
            by_type[issue.issue_type] += 1
            severity_counts[issue.severity] += 1
        
        ethical_score = max(0, 100 - (len(self.issues) * 1.5))
        
        return {
            'total_issues': len(self.issues),
            'ethical_score': round(ethical_score, 1),
            'issues_by_severity': dict(severity_counts),
            'issues_by_type': dict(by_type),
            'issues': self.issues
        }
