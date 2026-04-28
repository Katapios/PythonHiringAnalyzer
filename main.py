import logging
import re
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
}

BASE_URL = "https://career.habr.com/vacancies"
REQUEST_TIMEOUT = 15
MAX_DETAIL_WORKERS = 4
DETAIL_REQUEST_DELAY = 0.2
SEARCH_REQUEST_DELAY = 0.5
MAX_SEARCH_PAGES = 2
MAX_VACANCIES_PER_ROLE = 18
MAX_EXAMPLES_PER_ROLE = 5

ROLE_CATALOG = [
    {
        "label_ru": "Python разработчик",
        "label_en": "Python Developer",
        "queries": ["python developer", "python разработчик", "python engineer"],
        "ai_keywords": ["Python", "FastAPI", "Django", "REST API", "SQL", "PostgreSQL", "Docker", "asyncio", "microservices", "pytest"],
    },
    {
        "label_ru": "Java разработчик",
        "label_en": "Java Developer",
        "queries": ["java developer", "java разработчик", "java engineer"],
        "ai_keywords": ["Java", "Spring Boot", "Hibernate", "Microservices", "REST API", "Kafka", "SQL", "Docker", "Kubernetes", "JUnit"],
    },
    {
        "label_ru": "Frontend разработчик",
        "label_en": "Frontend Developer",
        "queries": ["frontend developer", "frontend разработчик", "react developer", "javascript developer"],
        "ai_keywords": ["JavaScript", "TypeScript", "React", "Next.js", "Redux", "HTML", "CSS", "REST API", "GraphQL", "Webpack"],
    },
    {
        "label_ru": "Backend разработчик",
        "label_en": "Backend Developer",
        "queries": ["backend developer", "backend разработчик", "backend engineer"],
        "ai_keywords": ["Backend", "REST API", "Microservices", "SQL", "PostgreSQL", "Redis", "Kafka", "Docker", "Kubernetes", "CI/CD"],
    },
    {
        "label_ru": "Fullstack разработчик",
        "label_en": "Fullstack Developer",
        "queries": ["fullstack developer", "fullstack разработчик", "full stack developer"],
        "ai_keywords": ["JavaScript", "TypeScript", "React", "Node.js", "REST API", "SQL", "PostgreSQL", "Docker", "AWS", "CI/CD"],
    },
    {
        "label_ru": "DevOps инженер",
        "label_en": "DevOps Engineer",
        "queries": ["devops engineer", "devops инженер", "site reliability engineer", "sre"],
        "ai_keywords": ["DevOps", "CI/CD", "Docker", "Kubernetes", "Terraform", "Ansible", "AWS", "Linux", "Monitoring", "Infrastructure as Code"],
    },
    {
        "label_ru": "Data Scientist",
        "label_en": "Data Scientist",
        "queries": ["data scientist", "data science", "специалист по data science"],
        "ai_keywords": ["Python", "Machine Learning", "Pandas", "NumPy", "SQL", "A/B Testing", "Statistics", "scikit-learn", "Data Analysis", "Experiment Design"],
    },
    {
        "label_ru": "ML инженер",
        "label_en": "Machine Learning Engineer",
        "queries": ["machine learning engineer", "ml engineer", "инженер машинного обучения"],
        "ai_keywords": ["Machine Learning", "Python", "PyTorch", "TensorFlow", "MLOps", "Docker", "Kubernetes", "Feature Engineering", "Model Deployment", "Airflow"],
    },
    {
        "label_ru": "QA инженер",
        "label_en": "QA Engineer",
        "queries": ["qa engineer", "qa инженер", "test engineer", "тестировщик"],
        "ai_keywords": ["QA", "Test Automation", "Selenium", "Playwright", "API Testing", "Postman", "pytest", "CI/CD", "Regression Testing", "Test Cases"],
    },
    {
        "label_ru": "Android разработчик",
        "label_en": "Android Developer",
        "queries": ["android developer", "android разработчик"],
        "ai_keywords": ["Android", "Kotlin", "Java", "Jetpack Compose", "MVVM", "REST API", "Coroutines", "Room", "Gradle", "Firebase"],
    },
    {
        "label_ru": "iOS разработчик",
        "label_en": "iOS Developer",
        "queries": ["ios developer", "ios разработчик"],
        "ai_keywords": ["iOS", "Swift", "UIKit", "SwiftUI", "MVVM", "REST API", "Core Data", "Xcode", "Unit Testing", "App Store"],
    },
    {
        "label_ru": "Product Manager",
        "label_en": "Product Manager",
        "queries": ["product manager", "продакт менеджер", "менеджер продукта"],
        "ai_keywords": ["Product Management", "Roadmap", "Backlog", "User Research", "A/B Testing", "Analytics", "Stakeholder Management", "Go-to-Market", "Jira", "SQL"],
    },
    {
        "label_ru": "Менеджер разработки ПО",
        "label_en": "Software Development Manager",
        "queries": ["software development manager", "менеджер разработки", "руководитель разработки"],
        "ai_keywords": ["Software Development Manager", "Team Leadership", "People Management", "Delivery Management", "Agile", "Scrum", "Hiring", "Mentoring", "Roadmap Planning", "Cross-functional Leadership"],
    },
    {
        "label_ru": "Инженерный менеджер",
        "label_en": "Engineering Manager",
        "queries": ["engineering manager", "инженерный менеджер", "технический менеджер"],
        "ai_keywords": ["Engineering Manager", "People Management", "Technical Leadership", "System Design", "Architecture", "Stakeholder Management", "Performance Reviews", "Hiring", "Mentoring", "Agile Delivery"],
    },
    {
        "label_ru": "Директор разработки ПО",
        "label_en": "Director of Software Engineering",
        "queries": ["director of software engineering", "директор по разработке", "директор разработки"],
        "ai_keywords": ["Director of Software Engineering", "Engineering Strategy", "Organization Scaling", "Budgeting", "Cross-functional Leadership", "Engineering Excellence", "Portfolio Management", "Executive Communication", "Transformation", "Delivery Governance"],
    },
    {
        "label_ru": "Руководитель разработки / R&D",
        "label_en": "Head of Development / R&D",
        "queries": ["head of development", "head of r&d", "руководитель разработки", "руководитель r&d"],
        "ai_keywords": ["Head of Development", "R&D", "Technical Strategy", "Innovation", "Architecture", "Team Leadership", "Product Delivery", "Hiring", "Process Improvement", "Stakeholder Management"],
    },
    {
        "label_ru": "Full-stack разработчик с уклоном в AI",
        "label_en": "Full-stack Developer (AI-focused)",
        "queries": ["full-stack developer ai", "fullstack developer ai", "ai developer", "llm engineer", "generative ai engineer"],
        "ai_keywords": ["LLM", "Generative AI", "Prompt Engineering", "RAG", "OpenAI API", "Python", "TypeScript", "React", "Vector Database", "AI Agents"],
    },
]

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
THREAD_LOCAL = local()

SKILL_MAPPING = {
    "python": ["python", "django", "flask", "fastapi", "sqlalchemy", "pandas", "numpy", "scikit-learn", "pytest"],
    "java": ["java", "spring", "spring boot", "hibernate", "maven", "gradle", "kotlin", "scala"],
    "javascript": ["javascript", "typescript", "node.js", "nodejs", "express", "nest.js", "nestjs", "react", "vue", "angular", "jquery"],
    "database": ["sql", "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch", "cassandra", "clickhouse"],
    "devops": ["docker", "kubernetes", "k8s", "jenkins", "gitlab", "github actions", "terraform", "ansible", "linux", "bash", "nginx"],
    "cloud": ["aws", "azure", "gcp", "google cloud", "yandex cloud", "openstack"],
    "qa": ["pytest", "junit", "selenium", "postman", "jmeter", "testrail", "allure", "cypress", "playwright"],
    "methodology": ["agile", "scrum", "kanban", "jira", "confluence", "trello"],
    "mobile": ["android", "ios", "swift", "kotlin", "react native", "flutter", "xamarin"],
    "datascience": ["tensorflow", "pytorch", "keras", "spark", "hadoop", "airflow", "ml", "machine learning", "deep learning", "nlp"],
    "frontend": ["html", "css", "sass", "less", "webpack", "vite", "tailwind", "bootstrap", "next.js", "nuxt"],
    "backend": ["rest", "graphql", "grpc", "rabbitmq", "kafka", "celery", "microservices", "redis"],
    "security": ["owasp", "ssl", "oauth", "jwt", "penetration testing", "vulnerability assessment"],
    "vcs": ["git", "github", "gitlab", "bitbucket"],
    "analytics": ["power bi", "tableau", "superset", "dbt"],
}

ALL_SKILLS = sorted({skill for skills in SKILL_MAPPING.values() for skill in skills})
SKILL_PATTERNS = {}
SKILL_ALIAS_TO_CANONICAL = {}
SALARY_NUMBER_PATTERN = re.compile(r"\d[\d\s\xa0]*")

for skill in ALL_SKILLS:
    variants = {
        skill,
        skill.replace("-", " "),
        skill.replace(" ", "-"),
    }
    SKILL_PATTERNS[skill] = [re.compile(r"\b" + re.escape(variant) + r"\b") for variant in variants]
    for variant in variants:
        normalized_variant = re.sub(r"[-\s]+", " ", variant.strip().lower())
        SKILL_ALIAS_TO_CANONICAL[normalized_variant] = skill


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_thread_session() -> requests.Session:
    session = getattr(THREAD_LOCAL, "session", None)
    if session is None:
        session = create_session()
        THREAD_LOCAL.session = session
    return session


def fetch_page(session: requests.Session, url: str, params: Optional[Dict] = None) -> BeautifulSoup:
    resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def normalize_text_token(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def normalize_skill_name(skill: str) -> str:
    token = re.sub(r"[-\s]+", " ", skill.strip().lower())
    return SKILL_ALIAS_TO_CANONICAL.get(token, token)


def extract_skills_from_text(text: str) -> List[str]:
    if not text:
        return []

    text_lower = text.lower()
    found_skills = set()

    for skill, patterns in SKILL_PATTERNS.items():
        if any(pattern.search(text_lower) for pattern in patterns):
            found_skills.add(skill)

    return sorted(found_skills)


def extract_explicit_skills(soup: BeautifulSoup) -> List[str]:
    selectors = [
        'a[class*="tag"]',
        'span[class*="tag"]',
        'a[class*="skill"]',
        'span[class*="skill"]',
        'li[class*="skill"]',
    ]
    raw_skills = set()

    for selector in selectors:
        for elem in soup.select(selector):
            text = normalize_text_token(elem.get_text(" ", strip=True))
            if 1 < len(text) <= 40 and re.search(r"[a-zA-Zа-яА-Я0-9]", text):
                raw_skills.add(normalize_skill_name(text))

    return sorted(raw_skills)


def find_vacancy_cards(soup: BeautifulSoup) -> List[BeautifulSoup]:
    cards = soup.find_all("div", class_="vacancy-card")
    if not cards:
        cards = soup.find_all("div", class_="job-card")
    if not cards:
        cards = soup.find_all("article")
    return cards


def parse_salary(salary_text: str) -> Optional[Dict]:
    if not salary_text or salary_text == "не указана":
        return None

    numbers = [int(re.sub(r"\D", "", match)) for match in SALARY_NUMBER_PATTERN.findall(salary_text)]
    if not numbers:
        return None

    salary_lower = salary_text.lower()
    currency = "RUB"
    if "$" in salary_text or "usd" in salary_lower:
        currency = "USD"
    elif "€" in salary_text or "eur" in salary_lower:
        currency = "EUR"

    if len(numbers) == 1:
        salary_min, salary_max = numbers[0], numbers[0]
    else:
        salary_min, salary_max = min(numbers), max(numbers)

    return {
        "min": salary_min,
        "max": salary_max,
        "currency": currency,
        "raw": salary_text,
    }


def summarize_salaries(vacancies: List[Dict]) -> List[str]:
    buckets: Dict[str, List[int]] = {}

    for vacancy in vacancies:
        parsed = vacancy.get("salary_parsed")
        if not parsed:
            continue
        values = buckets.setdefault(parsed["currency"], [])
        values.append(parsed["min"])
        values.append(parsed["max"])

    if not buckets:
        return ["нет данных"]

    summaries = []
    for currency, values in buckets.items():
        summaries.append(
            f"{currency}: min {min(values):,}, median {int(statistics.median(values)):,}, max {max(values):,}".replace(",", " ")
        )
    return summaries


def get_vacancies_count(session: requests.Session, keyword: str) -> int:
    params = {"q": keyword, "page": 1}

    try:
        soup = fetch_page(session, BASE_URL, params=params)
        count_elem = soup.find("div", class_="vacancy-search__header-count")
        if count_elem:
            numbers = re.findall(r"\d+", count_elem.text)
            if numbers:
                return int(numbers[0])

        return len(find_vacancy_cards(soup))
    except requests.RequestException as e:
        logger.warning("Не удалось получить количество вакансий для '%s': %s", keyword, e)
        return 0
    except Exception as e:
        logger.warning("Ошибка при разборе списка вакансий для '%s': %s", keyword, e)
        return 0


def get_vacancy_details_robust(vacancy_url: str, title: str = "") -> Dict:
    result = {"description": "", "requirements": "", "skills_from_title": [], "skills_from_page": []}

    if title:
        result["skills_from_title"] = extract_skills_from_text(title)

    try:
        time.sleep(DETAIL_REQUEST_DELAY)
        soup = fetch_page(get_thread_session(), vacancy_url)

        selectors = [
            "div.job-description",
            "div.vacancy-description",
            "div.content",
            "div.vacancy__description",
            "article",
            'div[class*="description"]',
            'div[class*="Description"]',
            'div[class*="content"]',
        ]

        description_text = ""
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                description_text = elem.get_text(separator=" ", strip=True)
                if len(description_text) > 100:
                    break

        if not description_text or len(description_text) < 100:
            for div in soup.find_all("div"):
                div_text = div.get_text(separator=" ", strip=True)
                if 200 < len(div_text) < 5000:
                    description_text = div_text
                    break

        result["description"] = description_text

        requirements_elem = soup.find("div", class_="job-requirements")
        if not requirements_elem:
            requirements_elem = soup.find("div", class_="vacancy-requirements")
        if requirements_elem:
            result["requirements"] = requirements_elem.get_text(separator=" ", strip=True)

        result["skills_from_page"] = extract_explicit_skills(soup)
    except requests.RequestException as e:
        logger.warning("Не удалось загрузить вакансию %s: %s", vacancy_url, e)
    except Exception as e:
        logger.warning("Ошибка при парсинге вакансии %s: %s", vacancy_url, e)

    return result


def parse_vacancy_card(card: BeautifulSoup) -> Optional[Dict]:
    title_elem = (
        card.find("a", class_="vacancy-card__title-link")
        or card.find("a", class_="job__title-link")
        or card.find("a", href=re.compile(r"/vacancies/\d+"))
    )
    if not title_elem:
        return None

    title = title_elem.text.strip() if title_elem else "Не указано"
    href = title_elem.get("href", "")
    url = href if href.startswith("http") else f"https://career.habr.com{href}"

    company_elem = (
        card.find("div", class_="vacancy-card__company-title")
        or card.find("div", class_="job__company")
        or card.find("span", class_="company-name")
    )
    company = company_elem.text.strip() if company_elem else "Не указана"

    city_elem = (
        card.find("span", class_="vacancy-card__meta-location")
        or card.find("span", class_="job__location")
        or card.find("div", class_="location")
    )
    city = city_elem.text.strip() if city_elem else "Не указан"

    salary_elem = (
        card.find("div", class_="vacancy-card__salary")
        or card.find("div", class_="job__salary")
    )
    salary = salary_elem.text.strip() if salary_elem else "не указана"

    return {
        "title": title,
        "company": company,
        "city": city,
        "salary": salary,
        "salary_parsed": parse_salary(salary),
        "url": url,
        "skills": [],
    }


def collect_role_vacancies(session: requests.Session, queries: List[str], limit: int) -> Tuple[List[Dict], int, Dict[str, int]]:
    vacancy_map: Dict[str, Dict] = {}
    query_counts: Dict[str, int] = {}

    for query in queries:
        query_counts[query] = get_vacancies_count(session, query)

        for page in range(1, MAX_SEARCH_PAGES + 1):
            try:
                soup = fetch_page(session, BASE_URL, params={"q": query, "page": page})
            except requests.RequestException as e:
                logger.warning("Не удалось получить страницу %s для '%s': %s", page, query, e)
                break

            cards = find_vacancy_cards(soup)
            if not cards:
                break

            for card in cards:
                vacancy = parse_vacancy_card(card)
                if vacancy and vacancy["url"] not in vacancy_map:
                    vacancy_map[vacancy["url"]] = vacancy
                if len(vacancy_map) >= limit:
                    break

            if len(vacancy_map) >= limit:
                break

            time.sleep(SEARCH_REQUEST_DELAY)

        if len(vacancy_map) >= limit:
            break

    estimated_market_count = max(query_counts.values(), default=0)
    return list(vacancy_map.values()), estimated_market_count, query_counts


def enrich_vacancies_with_details(vacancies: List[Dict]) -> Counter:
    skill_counter = Counter()

    with ThreadPoolExecutor(max_workers=MAX_DETAIL_WORKERS) as executor:
        future_to_row = {
            executor.submit(get_vacancy_details_robust, row["url"], row["title"]): row
            for row in vacancies
        }

        for future in as_completed(future_to_row):
            row = future_to_row[future]
            details = future.result()

            full_text = f"{row['title']} {details.get('description', '')} {details.get('requirements', '')}"
            skills = set(extract_skills_from_text(full_text))
            skills.update(details.get("skills_from_title", []))
            skills.update(details.get("skills_from_page", []))

            row["skills"] = sorted(skills)
            row["description"] = details.get("description", "")
            row["requirements"] = details.get("requirements", "")
            for skill in row["skills"]:
                skill_counter[skill] += 1

    return skill_counter


def normalize_multiline_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def analyze_demand() -> List[Dict]:
    results = []
    total = len(ROLE_CATALOG)

    print("\n" + "=" * 60)
    print("📊 АНАЛИЗ РОЛЕЙ, НАВЫКОВ И ЗАРПЛАТ В IT")
    print("=" * 60)

    with create_session() as session:
        for index, role in enumerate(ROLE_CATALOG, 1):
            role_name = f"{role['label_ru']} / {role['label_en']}"
            print(f"\n[{index}/{total}] {role_name}...")

            vacancies, estimated_market_count, query_counts = collect_role_vacancies(
                session=session,
                queries=role["queries"],
                limit=MAX_VACANCIES_PER_ROLE,
            )
            print(f"  Оценка спроса по лучшему запросу: {estimated_market_count}")
            print(f"  Уникальных вакансий для анализа: {len(vacancies)}")

            skill_counter = enrich_vacancies_with_details(vacancies) if vacancies else Counter()
            print(f"  Найдено уникальных навыков: {len(skill_counter)}")

            results.append(
                {
                    "name": role_name,
                    "name_ru": role["label_ru"],
                    "name_en": role["label_en"],
                    "queries": role["queries"],
                    "ai_keywords": role.get("ai_keywords", []),
                    "vacancies": estimated_market_count,
                    "query_counts": query_counts,
                    "examples": vacancies[:MAX_EXAMPLES_PER_ROLE],
                    "skills_ranked": [skill for skill, _ in skill_counter.most_common()],
                    "all_skills": dict(skill_counter.most_common()),
                    "salary_summary": summarize_salaries(vacancies),
                    "analyzed_count": len(vacancies),
                }
            )

            time.sleep(SEARCH_REQUEST_DELAY)

    results.sort(key=lambda item: item["vacancies"], reverse=True)
    return results


def print_results(results: List[Dict]) -> None:
    print("\n" + "🏆" * 25)
    print("ВОСТРЕБОВАННЫЕ IT-РОЛИ")
    print("🏆" * 25)

    print(f"\n{'№':<3} {'Роль':<40} {'Вакансий':<10}")
    print("-" * 70)
    for index, item in enumerate(results, 1):
        name = item["name"][:39]
        print(f"{index:<3} {name:<40} {item['vacancies']:>10}")

    print("\n" + "📊" * 25)
    print("НАВЫКИ И ЗАРПЛАТЫ ПО РОЛЯМ")
    print("📊" * 25)

    for index, item in enumerate(results, 1):
        print(f"\n{'=' * 70}")
        print(f"{index}. {item['name']}")
        print(f"   Оценка спроса: {item['vacancies']} | Проанализировано вакансий: {item['analyzed_count']}")
        print(f"   Запросы: {', '.join(item['queries'])}")
        print(f"   ATS/AI keywords: {', '.join(item['ai_keywords'])}")
        print(f"   Разбивка по запросам: {', '.join(f'{query}={count}' for query, count in item['query_counts'].items())}")
        print(f"   Зарплаты: {'; '.join(item['salary_summary'])}")
        print("-" * 70)

        if item["skills_ranked"]:
            print("\n   🔧 ПОЛНЫЙ СПИСОК НАВЫКОВ:")
            for skill in item["skills_ranked"]:
                count = item["all_skills"].get(skill, 0)
                print(f"      - {skill} ({count})")
        else:
            print("\n   ⚠️ Навыки не найдены")

        if item["examples"]:
            print("\n   📌 ПРИМЕРЫ ВАКАНСИЙ:")
            for vacancy in item["examples"]:
                print(f"\n      • {vacancy['title']}")
                print(f"        🏢 {vacancy['company']} | 📍 {vacancy['city']} | 💰 {vacancy['salary']}")
                if vacancy.get("skills"):
                    print(f"        🛠️ {', '.join(vacancy['skills'])}")
                if vacancy.get("requirements"):
                    print(f"        📋 Требования: {normalize_multiline_text(vacancy['requirements'])}")
                elif vacancy.get("description"):
                    print(f"        📄 Описание: {normalize_multiline_text(vacancy['description'])}")
        else:
            print("\n   📌 Примеры вакансий не найдены")


def save_to_file(results: List[Dict]) -> None:
    from datetime import datetime

    filename = f"it_market_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    with open(filename, "w", encoding="utf-8") as file:
        file.write("=" * 80 + "\n")
        file.write("ОТЧЕТ: ВОСТРЕБОВАННЫЕ IT-РОЛИ, НАВЫКИ И ЗАРПЛАТЫ\n")
        file.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        file.write("Источник: Habr Career\n")
        file.write("=" * 80 + "\n\n")

        for index, item in enumerate(results, 1):
            file.write(f"{index}. {item['name']}\n")
            file.write(f"   Оценка спроса: {item['vacancies']}\n")
            file.write(f"   Проанализировано вакансий: {item['analyzed_count']}\n")
            file.write(f"   Запросы: {', '.join(item['queries'])}\n")
            file.write(f"   ATS/AI keywords: {', '.join(item['ai_keywords'])}\n")
            file.write(f"   Разбивка по запросам: {', '.join(f'{query}={count}' for query, count in item['query_counts'].items())}\n")
            file.write(f"   Зарплаты: {'; '.join(item['salary_summary'])}\n")

            if item["skills_ranked"]:
                file.write("\n   Полный список навыков:\n")
                for skill in item["skills_ranked"]:
                    count = item["all_skills"].get(skill, 0)
                    file.write(f"      - {skill} ({count})\n")
            else:
                file.write("\n   Навыки не найдены\n")

            if item["examples"]:
                file.write("\n   Примеры вакансий:\n")
                for vacancy in item["examples"]:
                    file.write(f"      • {vacancy['title']}\n")
                    file.write(f"        Компания: {vacancy['company']} | Город: {vacancy['city']} | Зарплата: {vacancy['salary']}\n")
                    if vacancy.get("skills"):
                        file.write(f"        Навыки: {', '.join(vacancy['skills'])}\n")
                    if vacancy.get("requirements"):
                        file.write(f"        Требования: {normalize_multiline_text(vacancy['requirements'])}\n")
                    elif vacancy.get("description"):
                        file.write(f"        Описание: {normalize_multiline_text(vacancy['description'])}\n")
                    file.write(f"        Ссылка: {vacancy['url']}\n")
            file.write("\n" + "-" * 80 + "\n\n")

    print(f"\n💾 Полный отчет сохранен в файл: {filename}")


def main() -> None:
    print("\n" + "🚀" * 25)
    print("ПАРСЕР IT-ВАКАНСИЙ: РОЛИ, НАВЫКИ, ЗАРПЛАТЫ")
    print("Источник: Habr Career")
    print("🚀" * 25)

    try:
        results = analyze_demand()
        if not results:
            print("\n❌ Не удалось получить данные. Проверьте интернет-соединение.")
            return

        print_results(results)
        save_to_file(results)

        print("\n" + "✅" * 25)
        print("ГОТОВО! Анализ рынка IT завершен.")
        print("✅" * 25)
    except KeyboardInterrupt:
        print("\n\n⏹️ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
