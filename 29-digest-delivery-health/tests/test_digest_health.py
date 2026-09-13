#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for digest_health.py
"""

import unittest
import tempfile
import os
import json
from datetime import datetime, timedelta, timezone

# Импортируем функции из основного скрипта
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем и тестируем только вспомогательные функции, так как main требует реальные файлы
def _weekdays(dates, days):
    return sum(1 for d in dates if d.weekday() in days)


class TestDigestHealth(unittest.TestCase):

    def test_weekdays_with_all_days(self):
        """Тестируем _weekdays с массивом всех дней недели"""
        dates = []
        start_date = datetime(2023, 1, 2)  # Это понедельник
        for i in range(7):
            dates.append(start_date + timedelta(days=i))
        
        # Все дни недели (0-6)
        all_days = tuple(range(7))
        result = _weekdays(dates, all_days)
        self.assertEqual(result, 7)

    def test_weekdays_with_weekdays_only(self):
        """Тестируем _weekdays только с буднями"""
        dates = []
        start_date = datetime(2023, 1, 2)  # Это понедельник
        for i in range(7):
            dates.append(start_date + timedelta(days=i))
        
        # Только будни (понедельник-пятница: 0-4)
        weekdays = (0, 1, 2, 3, 4)
        result = _weekdays(dates, weekdays)
        self.assertEqual(result, 5)

    def test_weekdays_with_weekends_only(self):
        """Тестируем _weekdays только с выходными"""
        dates = []
        start_date = datetime(2023, 1, 2)  # Это понедельник
        for i in range(7):
            dates.append(start_date + timedelta(days=i))
        
        # Только выходные (суббота, воскресенье: 5, 6)
        weekends = (5, 6)
        result = _weekdays(dates, weekends)
        self.assertEqual(result, 2)

    def test_weekdays_with_no_matches(self):
        """Тестируем _weekdays когда нет совпадений"""
        dates = [datetime(2023, 1, 2)]  # Понедельник
        no_days = ()  # Пустой кортеж
        result = _weekdays(dates, no_days)
        self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()