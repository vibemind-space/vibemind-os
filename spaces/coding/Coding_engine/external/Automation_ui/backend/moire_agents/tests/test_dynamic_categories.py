"""
Test-Suite für Dynamisches Kategorie-System

Tests:
1. CategoryRegistry JSON Laden/Speichern
2. Auto-Approve nach 3 Vorschlägen
3. Hierarchische Kategorien (Parent-Child)
4. LLM System-Prompt Generierung
5. AgentDataFrame Integration
6. Kategorie-Validierung
"""

import unittest
import os
import json
import tempfile
import shutil
from datetime import datetime

# Pfad für Python-Module
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.category_registry import CategoryRegistry, get_category_registry, reset_category_registry


class TestCategoryRegistryBasics(unittest.TestCase):
    """Tests für grundlegende CategoryRegistry Funktionen."""
    
    def setUp(self):
        """Erstellt temporäres Test-Verzeichnis."""
        reset_category_registry()
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'test_categories.json')
        
        # Basis-Kategorien für Tests
        self.test_data = {
            "version": "1.0.0",
            "created": datetime.now().isoformat(),
            "lastUpdated": datetime.now().isoformat(),
            "categories": {
                "button": {
                    "description": "Clickable button element",
                    "examples": ["Submit Button", "Cancel Button"],
                    "usageCount": 10
                },
                "icon": {
                    "description": "Small graphical element",
                    "examples": ["Settings Icon"],
                    "usageCount": 5
                },
                "browser_icon": {
                    "description": "Browser application icon",
                    "examples": ["Chrome", "Firefox"],
                    "parent": "icon",
                    "usageCount": 3
                }
            },
            "pendingCategories": [],
            "settings": {
                "autoApproveThreshold": 3,
                "enableHierarchy": True,
                "maxPendingCategories": 50
            }
        }
        
        # Speichere Test-Daten
        with open(self.config_path, 'w') as f:
            json.dump(self.test_data, f)
        
        # Registry erstellen
        self.registry = CategoryRegistry(self.config_path)
    
    def tearDown(self):
        """Räumt temporäres Verzeichnis auf."""
        reset_category_registry()
        shutil.rmtree(self.temp_dir)
    
    def test_load_categories(self):
        """Test: Kategorien laden."""
        categories = self.registry.get_all_categories()
        self.assertIn("button", categories)
        self.assertIn("icon", categories)
        self.assertIn("browser_icon", categories)
        self.assertEqual(len(categories), 3)
    
    def test_get_category_info(self):
        """Test: Kategorie-Info abrufen."""
        cat = self.registry.get_category("button")
        self.assertIsNotNone(cat)
        self.assertEqual(cat.description, "Clickable button element")
        self.assertIn("Submit Button", cat.examples)
    
    def test_is_valid_category(self):
        """Test: Kategorie-Validierung."""
        self.assertTrue(self.registry.is_valid_category("button"))
        self.assertTrue(self.registry.is_valid_category("icon"))
        self.assertFalse(self.registry.is_valid_category("nonexistent"))
    
    def test_increment_usage(self):
        """Test: Usage-Counter erhöhen."""
        old_count = self.registry.get_category("button").usage_count
        self.registry.increment_usage("button")
        new_count = self.registry.get_category("button").usage_count
        self.assertEqual(new_count, old_count + 1)


class TestCategoryHierarchy(unittest.TestCase):
    """Tests für hierarchische Kategorien."""
    
    def setUp(self):
        """Setup mit hierarchischen Kategorien."""
        reset_category_registry()
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'hierarchy_categories.json')
        
        self.test_data = {
            "version": "1.0.0",
            "created": datetime.now().isoformat(),
            "lastUpdated": datetime.now().isoformat(),
            "categories": {
                "icon": {
                    "description": "Generic icon",
                    "examples": [],
                    "usageCount": 0
                },
                "browser_icon": {
                    "description": "Browser icon",
                    "examples": ["Chrome", "Firefox"],
                    "parent": "icon",
                    "usageCount": 0
                },
                "editor_icon": {
                    "description": "Editor icon", 
                    "examples": ["VS Code", "Sublime"],
                    "parent": "icon",
                    "usageCount": 0
                },
                "system_icon": {
                    "description": "System icon",
                    "examples": ["Settings", "Control Panel"],
                    "parent": "icon",
                    "usageCount": 0
                }
            },
            "pendingCategories": [],
            "settings": {
                "autoApproveThreshold": 3,
                "enableHierarchy": True,
                "maxPendingCategories": 50
            }
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(self.test_data, f)
        
        self.registry = CategoryRegistry(self.config_path)
    
    def tearDown(self):
        reset_category_registry()
        shutil.rmtree(self.temp_dir)
    
    def test_get_children(self):
        """Test: Kinder einer Kategorie abrufen."""
        children = self.registry.get_children("icon")
        self.assertEqual(len(children), 3)
        self.assertIn("browser_icon", children)
        self.assertIn("editor_icon", children)
        self.assertIn("system_icon", children)
    
    def test_get_parent(self):
        """Test: Parent einer Kategorie abrufen."""
        cat = self.registry.get_category("browser_icon")
        self.assertEqual(cat.parent, "icon")
    
    def test_leaf_categories(self):
        """Test: Leaf-Kategorien (ohne Kinder)."""
        leafs = self.registry.get_leaf_categories()
        self.assertNotIn("icon", leafs)  # Hat Kinder
        self.assertIn("browser_icon", leafs)
        self.assertIn("editor_icon", leafs)
    
    def test_parent_categories(self):
        """Test: Parent-Kategorien."""
        parents = self.registry.get_parent_categories()
        self.assertIn("icon", parents)


class TestAutoApprove(unittest.TestCase):
    """Tests für Auto-Approve Logik."""
    
    def setUp(self):
        """Setup mit niedrigem Auto-Approve Threshold."""
        reset_category_registry()
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'auto_approve_categories.json')
        
        self.test_data = {
            "version": "1.0.0",
            "created": datetime.now().isoformat(),
            "lastUpdated": datetime.now().isoformat(),
            "categories": {
                "icon": {
                    "description": "Generic icon",
                    "examples": [],
                    "usageCount": 0
                }
            },
            "pendingCategories": [],
            "settings": {
                "autoApproveThreshold": 3,
                "enableHierarchy": True,
                "maxPendingCategories": 50
            }
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(self.test_data, f)
        
        self.registry = CategoryRegistry(self.config_path)
    
    def tearDown(self):
        reset_category_registry()
        shutil.rmtree(self.temp_dir)
    
    def test_suggest_new_category(self):
        """Test: Neue Kategorie vorschlagen."""
        result = self.registry.suggest_category(
            name="game_icon",
            description="Gaming application icon",
            parent="icon",
            examples=["Steam", "Epic Games"]
        )
        
        self.assertEqual(result["action"], "pending")
        self.assertEqual(result["votes"], 1)
        pending = self.registry.get_pending_categories()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].name, "game_icon")
    
    def test_auto_approve_after_threshold(self):
        """Test: Auto-Approve nach 3 Vorschlägen."""
        # Erster Vorschlag
        result1 = self.registry.suggest_category(
            name="game_icon",
            description="Gaming icon",
            parent="icon"
        )
        self.assertEqual(result1["action"], "pending")
        self.assertEqual(result1["votes"], 1)
        
        # Zweiter Vorschlag
        result2 = self.registry.suggest_category(
            name="game_icon",
            description="Gaming application icon",
            parent="icon"
        )
        self.assertEqual(result2["action"], "pending")
        self.assertEqual(result2["votes"], 2)
        
        # Dritter Vorschlag - sollte auto-approved werden
        result3 = self.registry.suggest_category(
            name="game_icon",
            description="Gaming app icon",
            parent="icon"
        )
        self.assertEqual(result3["action"], "approved")
        self.assertTrue(self.registry.category_exists("game_icon"))
    
    def test_manual_approve(self):
        """Test: Manuelle Genehmigung."""
        # Vorschlagen
        self.registry.suggest_category(
            name="test_icon",
            description="Test icon"
        )
        
        # Manuell genehmigen
        success = self.registry.approve_pending("test_icon")
        self.assertTrue(success)
        self.assertTrue(self.registry.category_exists("test_icon"))
    
    def test_reject_pending(self):
        """Test: Vorschlag ablehnen."""
        # Vorschlagen
        self.registry.suggest_category(
            name="bad_category",
            description="Should be rejected"
        )
        
        # Ablehnen
        success = self.registry.reject_pending("bad_category")
        self.assertTrue(success)
        pending = self.registry.get_pending_categories()
        names = [p.name for p in pending]
        self.assertNotIn("bad_category", names)


class TestLLMPromptGeneration(unittest.TestCase):
    """Tests für LLM Prompt-Generierung."""
    
    def setUp(self):
        reset_category_registry()
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'prompt_categories.json')
        
        self.test_data = {
            "version": "1.0.0",
            "created": datetime.now().isoformat(),
            "lastUpdated": datetime.now().isoformat(),
            "categories": {
                "button": {
                    "description": "Clickable button",
                    "examples": ["Submit", "Cancel"],
                    "usageCount": 0
                },
                "icon": {
                    "description": "Small graphic",
                    "examples": ["Settings"],
                    "usageCount": 0
                },
                "browser_icon": {
                    "description": "Browser app icon",
                    "examples": ["Chrome"],
                    "parent": "icon",
                    "usageCount": 0
                }
            },
            "pendingCategories": [],
            "settings": {
                "autoApproveThreshold": 3,
                "enableHierarchy": True,
                "maxPendingCategories": 50
            }
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(self.test_data, f)
        
        self.registry = CategoryRegistry(self.config_path)
    
    def tearDown(self):
        reset_category_registry()
        shutil.rmtree(self.temp_dir)
    
    def test_build_classification_prompt(self):
        """Test: Classification Prompt generieren."""
        prompt = self.registry.build_classification_prompt()
        
        # Sollte Kategorien enthalten
        self.assertIn("button", prompt)
        self.assertIn("icon", prompt)
        self.assertIn("browser_icon", prompt)
        
        # Sollte NEW_CATEGORY Option enthalten
        self.assertIn("NEW_CATEGORY", prompt)
    
    def test_prompt_contains_descriptions(self):
        """Test: Prompt enthält Beschreibungen."""
        prompt = self.registry.build_classification_prompt()
        
        self.assertIn("Clickable button", prompt)
        self.assertIn("Browser app icon", prompt)
    
    def test_prompt_contains_examples(self):
        """Test: Prompt enthält Beispiele."""
        prompt = self.registry.build_classification_prompt()
        
        self.assertIn("Submit", prompt)
        self.assertIn("Chrome", prompt)


class TestRegistryPersistence(unittest.TestCase):
    """Tests für Registry-Persistenz."""
    
    def setUp(self):
        reset_category_registry()
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'persist_categories.json')
    
    def tearDown(self):
        reset_category_registry()
        shutil.rmtree(self.temp_dir)
    
    def test_create_new_registry(self):
        """Test: Neue Registry erstellen wenn Datei nicht existiert."""
        registry = CategoryRegistry(self.config_path)
        
        # Sollte existieren und gültige Kategorien haben
        self.assertTrue(os.path.exists(self.config_path))
        categories = registry.get_all_categories()
        self.assertGreater(len(categories), 0)
    
    def test_save_and_reload(self):
        """Test: Speichern und Neuladen."""
        registry1 = CategoryRegistry(self.config_path)
        
        # Kategorie hinzufügen
        registry1.add_category(
            name="test_cat",
            description="Test category",
            examples=["Example1"]
        )
        
        # Neue Instanz laden
        registry2 = CategoryRegistry(self.config_path)
        
        # Sollte Kategorie enthalten
        self.assertIn("test_cat", registry2.get_all_categories())
        cat = registry2.get_category("test_cat")
        self.assertEqual(cat.description, "Test category")


class TestStatistics(unittest.TestCase):
    """Tests für Kategorie-Statistiken."""
    
    def setUp(self):
        reset_category_registry()
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'stats_categories.json')
        
        test_data = {
            "version": "1.0.0",
            "created": datetime.now().isoformat(),
            "lastUpdated": datetime.now().isoformat(),
            "categories": {
                "button": {"description": "Button", "examples": [], "usageCount": 100},
                "icon": {"description": "Icon", "examples": [], "usageCount": 50},
                "new_cat": {"description": "New", "examples": [], "usageCount": 5, "createdByLlm": True}
            },
            "pendingCategories": [
                {"name": "pending_cat", "description": "Pending", "votes": 2, "suggestedBy": "llm",
                 "firstSuggested": datetime.now().isoformat(), "lastSuggested": datetime.now().isoformat()}
            ],
            "settings": {"autoApproveThreshold": 3, "enableHierarchy": True, "maxPendingCategories": 50}
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(test_data, f)
        
        self.registry = CategoryRegistry(self.config_path)
    
    def tearDown(self):
        reset_category_registry()
        shutil.rmtree(self.temp_dir)
    
    def test_get_statistics(self):
        """Test: Statistiken abrufen."""
        stats = self.registry.get_statistics()
        
        self.assertEqual(stats["totalCategories"], 3)
        self.assertEqual(stats["pendingCategories"], 1)
        self.assertIn("topCategories", stats)
    
    def test_llm_created_count(self):
        """Test: LLM-erstellte Kategorien zählen."""
        stats = self.registry.get_statistics()
        self.assertEqual(stats["llmCreatedCategories"], 1)


class TestAgentDataFrameIntegration(unittest.TestCase):
    """Tests für AgentDataFrame Integration."""
    
    def setUp(self):
        """Setup mit Test-Registry und DataFrame."""
        reset_category_registry()
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'adf_categories.json')
        
        # Test-Registry erstellen
        test_data = {
            "version": "1.0.0",
            "created": datetime.now().isoformat(),
            "lastUpdated": datetime.now().isoformat(),
            "categories": {
                "icon": {"description": "Generic icon", "examples": [], "usageCount": 0},
                "browser_icon": {"description": "Browser", "examples": [], "parent": "icon", "usageCount": 0},
                "button": {"description": "Button", "examples": [], "usageCount": 0}
            },
            "pendingCategories": [],
            "settings": {"autoApproveThreshold": 3, "enableHierarchy": True, "maxPendingCategories": 50}
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(test_data, f)
        
        # Temporär config_path setzen für get_category_registry
        os.environ['MOIRE_CATEGORY_REGISTRY'] = self.config_path
    
    def tearDown(self):
        reset_category_registry()
        shutil.rmtree(self.temp_dir)
        if 'MOIRE_CATEGORY_REGISTRY' in os.environ:
            del os.environ['MOIRE_CATEGORY_REGISTRY']
    
    def test_dataframe_category_lookup(self):
        """Test: DataFrame kann Kategorien abfragen."""
        import pandas as pd
        
        # Einfacher Test ohne volle AgentDataFrame Integration
        registry = CategoryRegistry(self.config_path)
        categories = registry.get_all_categories()
        
        self.assertIn("icon", categories)
        self.assertIn("browser_icon", categories)
        self.assertIn("button", categories)


def run_tests():
    """Führt alle Tests aus."""
    print("="*60)
    print("Dynamisches Kategorie-System - Test Suite")
    print("="*60)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Tests hinzufügen
    suite.addTests(loader.loadTestsFromTestCase(TestCategoryRegistryBasics))
    suite.addTests(loader.loadTestsFromTestCase(TestCategoryHierarchy))
    suite.addTests(loader.loadTestsFromTestCase(TestAutoApprove))
    suite.addTests(loader.loadTestsFromTestCase(TestLLMPromptGeneration))
    suite.addTests(loader.loadTestsFromTestCase(TestRegistryPersistence))
    suite.addTests(loader.loadTestsFromTestCase(TestStatistics))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentDataFrameIntegration))
    
    # Ausführen
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Zusammenfassung
    print("\n" + "="*60)
    print(f"Tests: {result.testsRun}")
    print(f"Fehler: {len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Erfolg: {'✅ JA' if result.wasSuccessful() else '❌ NEIN'}")
    print("="*60)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)