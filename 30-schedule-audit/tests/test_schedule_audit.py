import unittest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, mock_open

# Тестируем модуль schedule_audit.py
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schedule_audit import main


class TestScheduleAudit(unittest.TestCase):

    def setUp(self):
        # Создаем временные файлы для тестирования
        self.temp_dir = tempfile.mkdtemp()
        self.jobs_file = Path(self.temp_dir) / "jobs.json"
        self.audit_file = Path(self.temp_dir) / "usage_audit.jsonl"
        
        # Пример данных для jobs.json
        self.sample_jobs = [
            {
                "id": "job1",
                "name": "morning routine",
                "schedule": "0 6 * * *",
                "command": "echo 'morning'"
            },
            {
                "id": "job2", 
                "name": "research audit",
                "schedule": "0 12 * * *",
                "command": "echo 'research'"
            },
            {
                "id": "job3",
                "name": "translation task",
                "schedule": "0 14 * * *", 
                "command": "echo 'translate'"
            }
        ]
        
        # Пример данных для usage_audit.jsonl
        self.sample_audit_data = [
            {"job_id": "job1", "prompt_tokens": 50000, "completion_tokens": 10000},
            {"job_id": "job1", "prompt_tokens": 55000, "completion_tokens": 12000},
            {"job_id": "job2", "prompt_tokens": 150000, "completion_tokens": 80000},
            {"job_id": "job2", "prompt_tokens": 160000, "completion_tokens": 90000},
            {"job_id": "job3", "prompt_tokens": 250000, "completion_tokens": 100000},
            {"job_id": "job3", "prompt_tokens": 260000, "completion_tokens": 110000}
        ]

    def test_main_without_apply(self):
        """Тест основной функции без применения изменений"""
        # Записываем тестовые данные
        with open(self.jobs_file, 'w') as f:
            json.dump(self.sample_jobs, f)
            
        with open(self.audit_file, 'w') as f:
            for line in self.sample_audit_data:
                f.write(json.dumps(line) + '\n')
                
        # Проверяем, что файлы существуют
        self.assertTrue(self.jobs_file.exists())
        self.assertTrue(self.audit_file.exists())
        
        # Заменяем пути в модуле для тестирования
        with patch('schedule_audit.JOBS', self.jobs_file), \
             patch('schedule_audit.AUDIT', self.audit_file), \
             patch('sys.argv', ['schedule_audit.py']):
            # Вызываем main и проверяем, что она завершается успешно
            result = main()
            self.assertEqual(result, 0)

    def test_heavy_job_identification(self):
        """Тест идентификации тяжелых задач"""
        # Создаем задачу с высоким потреблением токенов
        high_usage_jobs = [
            {
                "id": "heavy_job",
                "name": "research audit",
                "schedule": "0 12 * * *",
                "command": "echo 'heavy task'"
            }
        ]
        
        # Данные с высоким потреблением
        high_usage_audit = [
            {"job_id": "heavy_job", "prompt_tokens": 200000, "completion_tokens": 100000},
            {"job_id": "heavy_job", "prompt_tokens": 220000, "completion_tokens": 110000}
        ]
        
        with open(self.jobs_file, 'w') as f:
            json.dump(high_usage_jobs, f)
            
        with open(self.audit_file, 'w') as f:
            for line in high_usage_audit:
                f.write(json.dumps(line) + '\n')
                
        with patch('schedule_audit.JOBS', self.jobs_file), \
             patch('schedule_audit.AUDIT', self.audit_file), \
             patch('sys.argv', ['schedule_audit.py']):
            result = main()
            self.assertEqual(result, 0)

    def test_flexible_task_detection(self):
        """Тест определения гибких задач для переноса"""
        # Задача, подходящая для переноса (гибкая, тяжелая, не критичная ко времени)
        flexible_jobs = [
            {
                "id": "flexible_job",
                "name": "weekly research audit",  # Соответствует FLEXIBLE паттерну
                "schedule": "0 14 * * *",  # Не соответствует TIME_CRITICAL часам
                "command": "echo 'flexible task'"
            }
        ]
        
        high_usage_audit = [
            {"job_id": "flexible_job", "prompt_tokens": 150000, "completion_tokens": 100000}
        ]
        
        with open(self.jobs_file, 'w') as f:
            json.dump(flexible_jobs, f)
            
        with open(self.audit_file, 'w') as f:
            for line in high_usage_audit:
                f.write(json.dumps(line) + '\n')
                
        with patch('schedule_audit.JOBS', self.jobs_file), \
             patch('schedule_audit.AUDIT', self.audit_file), \
             patch('sys.argv', ['schedule_audit.py']):
            result = main()
            self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()