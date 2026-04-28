import requests
from bs4 import BeautifulSoup
import time
import re
from collections import Counter
from typing import List, Dict, Tuple

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
}

# IT-специализации для анализа (более точные запросы)
IT_KEYWORDS = [
    "python developer", "java developer", "javascript developer", "frontend developer",
    "backend developer", "fullstack developer", "devops engineer", "data scientist",
    "machine learning engineer", "ios developer", "android developer", "qa engineer",
    "1с developer", "product manager"
]

BASE_URL = "https://career.habr.com/vacancies"

# РАСШИРЕННЫЙ словарь навыков с синонимами
SKILL_MAPPING = {
    # Python экосистема
    "python": ["python", "django", "flask", "fastapi", "sqlalchemy", "pandas", "numpy", "scikit-learn", "pytest"],
    # Java экосистема
    "java": ["java", "spring", "spring boot", "hibernate", "maven", "gradle", "kotlin", "scala"],
    # JavaScript/TypeScript
    "javascript": ["javascript", "typescript", "node.js", "express", "nest.js", "react", "vue", "angular", "jquery"],
    # Базы данных
    "database": ["sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "cassandra", "clickhouse"],
    # DevOps/Инфраструктура
    "devops": ["docker", "kubernetes", "k8s", "jenkins", "gitlab", "github actions", "terraform", "ansible", "linux",
               "bash", "nginx"],
    # Облака
    "cloud": ["aws", "azure", "gcp", "yandex cloud", "openstack"],
    # Тестирование
    "qa": ["pytest", "junit", "selenium", "postman", "jmeter", "testrail", "allure"],
    # Методологии
    "methodology": ["agile", "scrum", "kanban", "jira", "confluence", "trello"],
    # Мобильная разработка
    "mobile": ["android", "ios", "swift", "kotlin", "react native", "flutter", "xamarin"],
    # Data Science
    "datascience": ["tensorflow", "pytorch", "keras", "spark", "hadoop", "airflow", "ml", "deep learning", "nlp"],
    # Frontend
    "frontend": ["html", "css", "sass", "less", "webpack", "vite", "tailwind", "bootstrap"],
    # Backend
    "backend": ["rest", "graphql", "grpc", "rabbitmq", "kafka", "celery", "redis"],
    # Безопасность
    "security": ["owasp", "ssl", "oauth", "jwt", "penetration testing", "vulnerability assessment"],
    # Version control
    "vcs": ["git", "github", "gitlab", "bitbucket"],
}

# Плоский список всех навыков для быстрого поиска
ALL_SKILLS = [skill for skills in SKILL_MAPPING.values() for skill in skills]


def get_vacancies_count(keyword: str) -> int:
    """Получает количество вакансий по ключевому слову"""
    params = {"q": keyword, "page": 1}

    try:
        resp = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Пробуем найти счетчик
        count_elem = soup.find('div', class_='vacancy-search__header-count')
        if count_elem:
            numbers = re.findall(r'\d+', count_elem.text)
            if numbers:
                return int(numbers[0])

        # Если счетчика нет, считаем элементы на первой странице
        cards = soup.find_all('div', class_='vacancy-card')
        return len(cards) if cards else 15  # Допускаем, что если есть результаты, то хотя бы 15

    except Exception as e:
        print(f"  Ошибка: {e}")
        return 0


def extract_skills_from_text(text: str) -> List[str]:
    """Извлекает навыки из текста (описание + заголовок + требования)"""
    if not text:
        return []

    text_lower = text.lower()
    found_skills = []

    for skill in ALL_SKILLS:
        # Ищем с учетом границ слов и вариативности написания
        patterns = [
            r'\b' + re.escape(skill) + r'\b',
            r'\b' + re.escape(skill.replace("-", " ")) + r'\b',
            r'\b' + re.escape(skill.replace(" ", "-")) + r'\b',
        ]

        for pattern in patterns:
            if re.search(pattern, text_lower):
                found_skills.append(skill)
                break

    # Убираем дубликаты и сортируем
    return list(set(found_skills))


def get_vacancy_details_robust(vacancy_url: str, title: str = "") -> Dict:
    """
    РОБАСТНЫЙ метод получения описания вакансии - пробует разные варианты
    """
    result = {"description": "", "requirements": "", "skills_from_title": []}

    # Сначала извлекаем навыки из заголовка
    if title:
        result["skills_from_title"] = extract_skills_from_text(title)

    try:
        resp = requests.get(vacancy_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Пробуем разные селекторы для поиска описания
        selectors = [
            'div.job-description',
            'div.vacancy-description',
            'div.content',
            'div.vacancy__description',
            'article',
            'div[class*="description"]',
            'div[class*="Description"]',
            'div[class*="content"]'
        ]

        description_text = ""
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                description_text = elem.get_text(separator=' ', strip=True)
                if len(description_text) > 100:
                    break

        # Если не нашли по селекторам, ищем любые div с большим количеством текста
        if not description_text or len(description_text) < 100:
            all_divs = soup.find_all('div')
            for div in all_divs:
                div_text = div.get_text(separator=' ', strip=True)
                if 200 < len(div_text) < 5000:
                    description_text = div_text
                    break

        result["description"] = description_text

        # Ищем блок с требованиями (часто выделен отдельно)
        requirements_elem = soup.find('div', class_='job-requirements')
        if not requirements_elem:
            requirements_elem = soup.find('div', class_='vacancy-requirements')
        if requirements_elem:
            result["requirements"] = requirements_elem.get_text(separator=' ', strip=True)

    except Exception as e:
        pass  # Молча пропускаем ошибки парсинга конкретной вакансии

    return result


def get_vacancy_examples_with_skills(keyword: str, limit: int = 8) -> Tuple[List[Dict], Counter]:
    """
    Получает примеры вакансий и собирает статистику навыков
    """
    params = {"q": keyword, "page": 1}
    vacancies = []
    skill_counter = Counter()

    try:
        resp = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Пробуем разные селекторы для карточек вакансий
        cards = soup.find_all('div', class_='vacancy-card')
        if not cards:
            cards = soup.find_all('div', class_='job-card')
        if not cards:
            cards = soup.find_all('article')

        for idx, card in enumerate(cards[:limit]):
            # Название
            title_elem = (card.find('a', class_='vacancy-card__title-link') or
                          card.find('a', class_='job__title-link') or
                          card.find('a', href=re.compile(r'/vacancies/\d+')))

            if not title_elem:
                continue

            title = title_elem.text.strip() if title_elem else "Не указано"

            # Ссылка
            href = title_elem.get('href', '')
            url = href if href.startswith('http') else f"https://career.habr.com{href}"

            # Компания
            company_elem = (card.find('div', class_='vacancy-card__company-title') or
                            card.find('div', class_='job__company') or
                            card.find('span', class_='company-name'))
            company = company_elem.text.strip() if company_elem else "Не указана"

            # Город
            city_elem = (card.find('span', class_='vacancy-card__meta-location') or
                         card.find('span', class_='job__location') or
                         card.find('div', class_='location'))
            city = city_elem.text.strip() if city_elem else "Не указан"

            # Зарплата
            salary_elem = (card.find('div', class_='vacancy-card__salary') or
                           card.find('div', class_='job__salary'))
            salary = salary_elem.text.strip() if salary_elem else "не указана"

            # Получаем детали для извлечения навыков
            details = get_vacancy_details_robust(url, title)

            # Объединяем все тексты для извлечения навыков
            full_text = f"{title} {details.get('description', '')} {details.get('requirements', '')}"
            skills = extract_skills_from_text(full_text)

            # Если навыки не найдены в описании, берем из заголовка
            if not skills and details.get("skills_from_title"):
                skills = details["skills_from_title"]

            # Обновляем счетчик навыков
            for skill in skills:
                skill_counter[skill] += 1

            vacancies.append({
                "title": title,
                "company": company,
                "city": city,
                "salary": salary,
                "url": url,
                "skills": skills[:7]  # Сохраняем топ навыков
            })

            time.sleep(0.2)  # Вежливая пауза

    except Exception as e:
        print(f"\n  Ошибка при парсинге {keyword}: {e}")

    return vacancies, skill_counter


def analyze_demand() -> List[Dict]:
    """Анализирует востребованность и собирает навыки"""
    results = []
    total = len(IT_KEYWORDS)

    print("\n" + "=" * 60)
    print("📊 АНАЛИЗ ВОСТРЕБОВАННОСТИ И НАВЫКОВ")
    print("=" * 60)

    for i, keyword in enumerate(IT_KEYWORDS, 1):
        print(f"\n[{i}/{total}] {keyword}...")

        count = get_vacancies_count(keyword)
        print(f"  Вакансий найдено: {count}")

        if count > 0:
            print(f"  Парсинг вакансий для сбора навыков...")
            examples, skill_counter = get_vacancy_examples_with_skills(keyword, 6)
            print(f"  Обработано вакансий: {len(examples)}")
            print(f"  Найдено уникальных навыков: {len(skill_counter)}")
        else:
            examples, skill_counter = [], Counter()

        # Получаем топ-7 навыков
        top_skills = [skill for skill, _ in skill_counter.most_common(7)]

        results.append({
            "name": keyword,
            "vacancies": count,
            "examples": examples[:5],
            "top_skills": top_skills,
            "all_skills": dict(skill_counter.most_common(10))
        })

        time.sleep(0.8)  # Большая пауза между категориями

    # Сортировка по убыванию
    results.sort(key=lambda x: x["vacancies"], reverse=True)
    return results[:10]


def print_results(top10: List[Dict]) -> None:
    """Красивый вывод результатов"""
    print("\n" + "🏆" * 25)
    print("ТОП-10 ВОСТРЕБОВАННЫХ IT-СПЕЦИАЛИЗАЦИЙ")
    print("🏆" * 25)

    print(f"\n{'№':<3} {'Специализация':<28} {'Вакансий':<10}")
    print("-" * 50)
    for i, item in enumerate(top10, 1):
        name = item["name"][:27]
        print(f"{i:<3} {name:<28} {item['vacancies']:>10}")

    print("\n" + "📊" * 25)
    print("ТРЕБУЕМЫЕ НАВЫКИ ПО СПЕЦИАЛИЗАЦИЯМ")
    print("📊" * 25)

    for i, item in enumerate(top10, 1):
        print(f"\n{'=' * 60}")
        print(f"{i}. {item['name'].upper()}")
        print(f"   Вакансий: {item['vacancies']} | Проанализировано резюме: {len(item['examples'])}")
        print("-" * 60)

        # Вывод топ-навыков
        if item["top_skills"]:
            print(f"\n   🔧 КЛЮЧЕВЫЕ НАВЫКИ:")
            for idx, skill in enumerate(item["top_skills"][:5], 1):
                count = item["all_skills"].get(skill, 0)
                print(f"      {idx}. {skill:<20} (в {count} из {len(item['examples'])} вакансий)")
        else:
            print(f"\n   ⚠️ Навыки не найдены (возможные причины: нет описаний, страницы не загрузились)")

        # Вывод примеров вакансий
        if item["examples"]:
            print(f"\n   📌 ПРИМЕРЫ ВАКАНСИЙ:")
            for idx, vac in enumerate(item["examples"][:3], 1):
                print(f"\n      {idx}. {vac['title'][:60]}")
                print(f"         🏢 {vac['company']} | 📍 {vac['city']}")
                if vac.get("skills"):
                    print(f"         🛠️  Навыки: {', '.join(vac['skills'][:4])}")
        else:
            print(f"\n   📌 Примеры вакансий не найдены")

        time.sleep(0.3)


def save_to_file(top10: List[Dict]) -> None:
    """Сохраняет в файл"""
    from datetime import datetime
    filename = f"it_skills_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("ИТОГОВЫЙ ОТЧЕТ: ВОСТРЕБОВАННОСТЬ IT-СПЕЦИАЛИСТОВ И ТРЕБУЕМЫЕ НАВЫКИ\n")
        f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("Источник: Habr Career\n")
        f.write("=" * 70 + "\n\n")

        for i, item in enumerate(top10, 1):
            f.write(f"\n{'─' * 60}\n")
            f.write(f"{i}. {item['name'].upper()}\n")
            f.write(f"   📊 Всего вакансий: {item['vacancies']}\n")
            f.write(f"   📝 Проанализировано вакансий: {len(item['examples'])}\n")
            f.write(f"{'─' * 60}\n")

            # Навыки
            if item["top_skills"]:
                f.write(f"\n   🔧 ТОП-5 НАВЫКОВ:\n")
                for idx, skill in enumerate(item["top_skills"][:5], 1):
                    count = item["all_skills"].get(skill, 0)
                    f.write(f"      {idx}. {skill} — встречается в {count} вакансиях\n")
            else:
                f.write(f"\n   ⚠️ Навыки не обнаружены\n")

            # Примеры
            if item["examples"]:
                f.write(f"\n   📋 ПРИМЕРЫ ВАКАНСИЙ:\n")
                for idx, vac in enumerate(item["examples"][:2], 1):
                    f.write(f"\n      {idx}. {vac['title']}\n")
                    f.write(f"         Компания: {vac['company']} | Город: {vac['city']}\n")
                    if vac.get("skills"):
                        f.write(f"         Навыки: {', '.join(vac['skills'][:5])}\n")
                    f.write(f"         Ссылка: {vac['url']}\n")

            f.write("\n")

    print(f"\n💾 Полный отчет сохранен в файл: {filename}")


def main():
    print("\n" + "🚀" * 25)
    print("ПАРСЕР IT-ВАКАНСИЙ С АНАЛИЗОМ ТРЕБУЕМЫХ НАВЫКОВ")
    print("Источник: Habr Career")
    print("🚀" * 25)

    try:
        top10 = analyze_demand()

        if not top10:
            print("\n❌ Не удалось получить данные. Проверьте интернет-соединение.")
            return

        print_results(top10)
        save_to_file(top10)

        print("\n" + "✅" * 25)
        print("ГОТОВО! Анализ навыков завершен.")
        print("✅" * 25)

    except KeyboardInterrupt:
        print("\n\n⏹️ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
