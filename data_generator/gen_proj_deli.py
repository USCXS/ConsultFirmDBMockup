import random
from faker import Faker
from datetime import date, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy import or_
from collections import defaultdict
from data_generator.create_db import (Project, Consultant, BusinessUnit, Client, ProjectBillingRate, 
                                      ProjectExpense,Deliverable, ConsultantDeliverable, ConsultantTitleHistory, engine)
from data_generator.gen_cons_title_hist import get_growth_rate
fake = Faker()

def get_project_type():
    return random.choices(['Time and Material', 'Fixed'], weights=[0.6, 0.4])[0]

def generate_basic_project(session, current_year):
    project = Project(
        ClientID=random.choice(session.query(Client.ClientID).all())[0],
        UnitID=random.choice(session.query(BusinessUnit.BusinessUnitID).all())[0],
        Name=f"Project_{current_year}_{random.randint(1000, 9999)}",
        Type=get_project_type(),
        Status='Not Started',
        Progress=0
    )
    return project

def find_available_consultants(session, year):
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    
    available_consultants = session.query(Consultant).join(ConsultantTitleHistory).\
        filter(ConsultantTitleHistory.StartDate <= end_date).\
        filter(or_(ConsultantTitleHistory.EndDate >= start_date, ConsultantTitleHistory.EndDate == None)).\
        all()
    
    # Reset project count for each consultant at the start of the year
    for consultant in available_consultants:
        consultant.project_count = 0
    
    return available_consultants

def determine_project_count(available_consultants, growth_rate):
    base_count = len(available_consultants) // random.randint(3, 5)
    adjusted_count = int(base_count * (1 + growth_rate))
    return max(5, adjusted_count)

def assign_consultants_to_project(project, available_consultants, session):
    consultants_by_title = defaultdict(list)
    for consultant in available_consultants:
        current_title = session.query(ConsultantTitleHistory).\
            filter(ConsultantTitleHistory.ConsultantID == consultant.ConsultantID).\
            order_by(ConsultantTitleHistory.StartDate.desc()).first()
        
        if current_title:
            consultants_by_title[current_title.TitleID].append(consultant)

    assigned_consultants = []

    # Ensure at least one high-level consultant (Project Manager or above)
    higher_level_titles = [5, 6]
    for title_id in higher_level_titles:
        if consultants_by_title[title_id]:
            higher_level_consultant = random.choice(consultants_by_title[title_id])
            assigned_consultants.append(higher_level_consultant)
            consultants_by_title[title_id].remove(higher_level_consultant)
            break

    # Assign a mix of other consultants
    all_consultants = [c for consultants in consultants_by_title.values() for c in consultants]
    num_additional_consultants = min(len(all_consultants), random.randint(2, 5))
    
    assigned_consultants.extend(random.sample(all_consultants, num_additional_consultants))

    project.AssignedConsultants = assigned_consultants
    return assigned_consultants



def set_project_dates(project, current_year):
    if project.Type == 'Fixed':
        duration_months = random.randint(3, 24) 
    else:  # Time and Material
        duration_months = random.randint(1, 36)
    
    # Set the start date
    start_month = random.randint(1, 12)
    start_day = random.randint(1, 28)  # Avoid issues with February
    
    project.PlannedStartDate = date(current_year, start_month, start_day)
    project.PlannedEndDate = project.PlannedStartDate + timedelta(days=duration_months * 30)
    project.ActualStartDate = project.PlannedStartDate
    
    # Ensure the project duration is at least 1 day
    if project.PlannedEndDate <= project.PlannedStartDate:
        project.PlannedEndDate = project.PlannedStartDate + timedelta(days=1)
    
    return duration_months


def determine_project_completion(project, current_date):
    # Projects have a higher chance of completion if they're past their planned end date
    days_overdue = (current_date - project.PlannedEndDate).days
    base_completion_chance = 0.5 # Initialize a 50% on time completion chance
    
    if days_overdue > 0: # Increase chance for overdue project
        completion_chance = min(base_completion_chance + (days_overdue / 365), 0.95)
    else:
        total_planned_duration = (project.PlannedEndDate - project.PlannedStartDate).days
        if total_planned_duration > 0:
            elapsed_duration = (current_date - project.PlannedStartDate).days
            completion_chance = base_completion_chance * (elapsed_duration / total_planned_duration)
        else:
            completion_chance = 0  # Project hasn't started yet

    # Adjust based on progress
    if project.Progress > 0:
        completion_chance *= (project.Progress / 100)
    else:
        completion_chance = 0

    return random.random() < completion_chance

def update_project_status_and_progress(project, current_date):
    if current_date >= project.PlannedStartDate:
        project_duration = (project.PlannedEndDate - project.PlannedStartDate).days
        elapsed_duration = (current_date - project.PlannedStartDate).days
        project.Progress = min(int((elapsed_duration / project_duration) * 100), 99)
    else:
        project.Progress = 0

    if determine_project_completion(project, current_date):
        project.Status = 'Completed'
        project.ActualEndDate = min(current_date, project.PlannedEndDate)
        project.Progress = 100
    else:
        project.Status = 'In Progress' if current_date >= project.PlannedStartDate else 'Not Started'
        project.ActualEndDate = None
        if project.Status == 'In Progress':
            # Add some randomness to progress for ongoing projects
            project.Progress = min(99, max(0, int(project.Progress * random.uniform(0.8, 1.2))))

def calculate_consultant_costs(assigned_consultants, session):
    total_monthly_salary = 0
    for consultant in assigned_consultants:
        current_title = session.query(ConsultantTitleHistory).\
            filter(ConsultantTitleHistory.ConsultantID == consultant.ConsultantID).\
            order_by(ConsultantTitleHistory.StartDate.desc()).first()
        if current_title:
            total_monthly_salary += current_title.Salary / 12
    
    monthly_cost = total_monthly_salary * 1.3  # Adding 30% for overhead
    hourly_cost = monthly_cost / 160  # Assuming 160 working hours per month
    return monthly_cost, hourly_cost

def set_project_financials(project, monthly_cost, hourly_cost, duration_months):
    if project.Type == 'Fixed':
        total_cost = monthly_cost * duration_months
        profit_margin = random.uniform(0.15, 0.30)  # 15% to 30% profit margin
        project.Price = total_cost * (1 + profit_margin)
        project.PlannedHours = duration_months * 160  # Assuming 160 working hours per month
    else:  # Time and Material
        project.PlannedHours = duration_months * 160 
        project.Price = None
    project.PlannedHours = round(project.PlannedHours, -1)  # Round to nearest ten

    return project


def generate_project_billing_rates(session, project, assigned_consultants):
    billing_rates = []

    if project.Type == 'Time and Material':
        # Base billing rates for each title
        base_rates = {
            1: 100, 2: 150, 3: 200, 
            4: 250, 5: 300, 6: 400
        }

        assigned_titles = set()

        for consultant in assigned_consultants:
            current_title = session.query(ConsultantTitleHistory).\
                filter(ConsultantTitleHistory.ConsultantID == consultant.ConsultantID).\
                order_by(ConsultantTitleHistory.StartDate.desc()).first()
            
            if current_title and current_title.TitleID not in assigned_titles:
                base_rate = base_rates[current_title.TitleID]
                
                adjusted_rate = base_rate * random.uniform(1.0, 1.2)
                adjusted_rate = round(adjusted_rate / 5) * 5

                billing_rate = ProjectBillingRate(
                    ProjectID=project.ProjectID,
                    TitleID=current_title.TitleID,
                    Rate=adjusted_rate
                )
                billing_rates.append(billing_rate)
                assigned_titles.add(current_title.TitleID)

    return billing_rates

def generate_deliverables(project):
    num_deliverables = random.randint(3, 7)
    deliverables = []
    remaining_hours = project.PlannedHours
    project_duration = max(1, (project.PlannedEndDate - project.PlannedStartDate).days)

    for i in range(num_deliverables):
        is_last_deliverable = (i == num_deliverables - 1)
        
        if is_last_deliverable:
            planned_hours = remaining_hours
        else:
            min_hours = 10
            max_hours = max(min_hours, remaining_hours - (num_deliverables - i - 1) * min_hours)
            planned_hours = random.randint(min_hours, max_hours) if max_hours > min_hours else min_hours
            remaining_hours -= planned_hours

        start_date = project.PlannedStartDate if i == 0 else deliverables[-1].DueDate + timedelta(days=1)
        
        # Calculate the maximum possible duration for this deliverable
        max_duration = max(1, (project.PlannedEndDate - start_date).days)
        
        # Calculate the due date using max_duration
        if is_last_deliverable:
            due_date = project.PlannedEndDate
        else:
            deliverable_duration = min(max_duration, max(1, int((planned_hours / project.PlannedHours) * project_duration)))
            due_date = start_date + timedelta(days=deliverable_duration)

        deliverable = Deliverable(
            ProjectID=project.ProjectID,
            Name=f"Deliverable {i+1}",
            PlannedStartDate=start_date,
            ActualStartDate=start_date,
            Status='Not Started',
            DueDate=due_date,
            PlannedHours=planned_hours,
            ActualHours=0,
            Progress=0
        )
        deliverables.append(deliverable)

    return deliverables

def generate_consultant_deliverables(deliverables, assigned_consultants):
    consultant_deliverables = []

    for deliverable in deliverables:
        if not assigned_consultants:
            continue

        num_consultants = min(len(assigned_consultants), random.randint(1, 3))
        selected_consultants = random.sample(assigned_consultants, num_consultants)
        
        remaining_hours = deliverable.PlannedHours
        date_range = max(0, (deliverable.DueDate - deliverable.PlannedStartDate).days)
        
        while remaining_hours > 0:
            for consultant in selected_consultants:
                if remaining_hours <= 0:
                    break
                
                hours = min(random.randint(1, 8), remaining_hours)  # Max 8 hours per day
                if date_range > 0:
                    work_date = deliverable.PlannedStartDate + timedelta(days=random.randint(0, date_range))
                else:
                    work_date = deliverable.PlannedStartDate
                
                consultant_deliverable = ConsultantDeliverable(
                    ConsultantID=consultant.ConsultantID,
                    DeliverableID=deliverable.DeliverableID,
                    Date=work_date,
                    Hours=hours
                )
                consultant_deliverables.append(consultant_deliverable)
                remaining_hours -= hours

    return consultant_deliverables

def generate_project_expenses(project, deliverables):
    expenses = []
    if not deliverables:
        return expenses

    expense_categories = {
        'Travel': 0.8, 'Equipment': 0.6, 'Software Licenses': 0.7,
        'Training': 0.5, 'Miscellaneous': 0.3
    }

    num_expenses = random.randint(5, 15)
    project_duration = max(1, (project.PlannedEndDate - project.PlannedStartDate).days)
    
    for _ in range(num_expenses):
        category = random.choice(list(expense_categories.keys()))
        is_billable = random.random() < expense_categories[category]
        
        deliverable = random.choice(deliverables)
        
        if category in ['Travel', 'Equipment']:
            amount = random.uniform(500, 5000)
        elif category in ['Software Licenses', 'Training']:
            amount = random.uniform(100, 2000)
        else:  # Miscellaneous
            amount = random.uniform(50, 1000)
        amount = round(amount, 2)
        
        expense_date = project.PlannedStartDate + timedelta(days=random.randint(0, project_duration - 1))
        
        expense = ProjectExpense(
            ProjectID=project.ProjectID,
            DeliverableID=deliverable.DeliverableID,
            Date=expense_date,
            Amount=amount,
            Description=f"{category} expense for {deliverable.Name}",
            Category=category,
            IsBillable=is_billable
        )
        
        expenses.append(expense)
    
    return expenses

def generate_projects(start_year, end_year):
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        for current_year in range(start_year, end_year + 1):
            growth_rate = get_growth_rate(current_year)
            available_consultants = find_available_consultants(session, current_year)

            if not available_consultants:
                print(f"No available consultants for year {current_year}.")
                continue

            num_projects = determine_project_count(available_consultants, growth_rate)

            for _ in range(num_projects):
                project = generate_basic_project(session, current_year)
                assigned_consultants = assign_consultants_to_project(project, available_consultants, session)
                
                monthly_cost, hourly_cost = calculate_consultant_costs(assigned_consultants, session)
                duration_months = set_project_dates(project, current_year)
                project = set_project_financials(project, monthly_cost, hourly_cost, duration_months)

                session.add(project)
                session.flush()  # This will populate the ProjectID

                deliverables = generate_deliverables(project)
                session.add_all(deliverables)
                session.flush()

                consultant_deliverables = generate_consultant_deliverables(deliverables, assigned_consultants)
                session.add_all(consultant_deliverables)

                project_expenses = generate_project_expenses(project, deliverables)
                session.add_all(project_expenses)

                project.TotalExpenses = sum(expense.Amount for expense in project_expenses)

                if project.Type == 'Time and Material':
                    billing_rates = generate_project_billing_rates(session, project, assigned_consultants)
                    session.add_all(billing_rates)

                # Update project status and progress
                current_date = date(current_year, 12, 31)
                update_project_status_and_progress(project, current_date)

                # Update consultant availability
                for consultant in assigned_consultants:
                    consultant.project_count = getattr(consultant, 'project_count', 0) + 1
                
                # Filter out consultants who are already on 2 projects
                available_consultants = [c for c in available_consultants if getattr(c, 'project_count', 0) < 2]

            print(f"Year {current_year}: Generated {num_projects} projects")

        session.commit()
    except Exception as e:
        print(f"An error occurred: {e}")
        session.rollback()
    finally:
        session.close()


def main(start_year, end_year):
    print("Generating Project Data...")
    generate_projects(start_year, end_year)
    print("Complete")