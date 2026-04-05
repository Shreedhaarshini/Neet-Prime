from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
import os
import json
import re
import hashlib
from groq import Groq
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Avg, Sum, F, FloatField, ExpressionWrapper
from django.utils import timezone
from .models import Subject, QuestionLog, TestResult, Chapter

# Groq Client Initialization
client = Groq(api_key=os.getenv('GROQ_API_KEY'))

def get_question_hash(question_text):
    """Generate a stable SHA-256 hash for repeat prevention."""
    normalized_text = ' '.join(question_text.lower().split())
    return hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()

def fetch_ai_questions(chapters, difficulty, count=15):
    """Fetch AI questions and extraction using Regex for robustness."""
    prompt = (
        f"Generate exactly {count} NEET-standard MCQs. "
        f"Subject context: {', '.join(chapters)}. "
        f"Difficulty: {difficulty}. "
        "Return ONLY a valid JSON array of objects."
    )
    
    schema = "\nSchema: [{'question': 'string', 'options': ['A', 'B', 'C', 'D'], 'correct_answer': 'string', 'explanation': 'string'}]"
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile", 
            messages=[
                {"role": "system", "content": "You are a JSON generator. Do not include any introductory or concluding text. Return only a valid JSON array of objects."},
                {"role": "user", "content": prompt + schema}
            ],
            temperature=0.7
        )
        response_text = completion.choices[0].message.content.strip()
        
        # Advanced JSON extraction using Regex
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            clean_json = match.group(0)
            return json.loads(clean_json)
        
        return json.loads(response_text)
    except Exception as e:
        print(f"AI Extraction Error: {e}")
        return []

@csrf_exempt
@login_required
@require_POST
def generate_quiz(request):
    """API view to generate unique quiz questions based on specific chapters."""
    try:
        data = json.loads(request.body)
        chapter_names = data.get('chapter_names', [])
        difficulty = data.get('difficulty', 'Medium')
        
        if not chapter_names:
            return JsonResponse({"error": "No chapters selected."}, status=400)
            
        questions = fetch_ai_questions(chapter_names, difficulty, 15)
        
        if not questions:
            return JsonResponse({"error": "Neural engine failed to stabilize data."}, status=500)

        chapters_db = Chapter.objects.filter(name__in=chapter_names)
        primary_subject = chapters_db.first().subject if chapters_db.exists() else None
        
        test_result = TestResult.objects.create(
            user=request.user,
            subject=primary_subject,
            score=0,
            total_questions=len(questions),
            difficulty=difficulty,
            questions_data=questions
        )
        if chapters_db.exists():
            test_result.chapters_covered.set(chapters_db)
        
        # Stabilize and map question data
        for q in questions:
            q_text = q.get('question_text') or q.get('question')
            q['question_text'] = q_text
            
            # REPAIR: Ensure explanation is preserved or provided a fallback
            q['explanation'] = q.get('explanation') or q.get('reasoning') or "Review NCERT scientific context for deep processing."
            
            if 'answer' in q and 'correct_answer' not in q:
                q['correct_answer'] = q['answer']
            
            # REPAIR: Calculate the correct letter mapping
            options = q.get('options', [])
            correct_text = q.get('correct_answer', "").strip()
            q['correct_letter'] = "?"
            for idx, opt in enumerate(options):
                if opt.strip() == correct_text:
                    q['correct_letter'] = chr(65 + idx) # A, B, C, D
                    break

            q_hash = get_question_hash(q_text)
            QuestionLog.objects.create(
                user=request.user,
                subject=primary_subject or Subject.objects.first(),
                question_hash=q_hash
            )

        # REPAIR: Persist the stabilized questions to the database
        test_result.questions_data = questions
        test_result.save()
                
        return JsonResponse({"questions": questions, "test_id": test_result.id}, status=200)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Payload corruption."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)

@csrf_exempt
@login_required
@require_POST
def submit_quiz_score(request):
    """API view to finalize performance analytics."""
    try:
        data = json.loads(request.body)
        test_id = data.get('test_id')
        score = data.get('score')
        
        test_result = TestResult.objects.get(id=test_id, user=request.user)
        test_result.score = score
        test_result.user_answers = data.get('answers')
        test_result.save()
        
        return JsonResponse({"status": "success"}, status=200)
    except TestResult.DoesNotExist:
        return JsonResponse({"error": "Invalid diagnostic marker."}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@login_required
def result_detail(request, test_id):
    """Detailed review page with AI-driven analysis."""
    try:
        test = TestResult.objects.get(id=test_id, user=request.user)
    except TestResult.DoesNotExist:
        return redirect('dashboard')

    questions = test.questions_data or []
    user_answers = test.user_answers or []
    labels = ['A', 'B', 'C', 'D']
    
    processed_results = []
    recalculated_score = 0
    
    for i, q in enumerate(questions):
        # NEW: Handle possible dict structure in user_answers (from quiz.html payload)
        ans_entry = user_answers[i] if i < len(user_answers) else {}
        
        # PROMPT FIX: Robust variable extraction before usage
        user_choice = ans_entry.get('selected_answer', "Unanswered") if isinstance(ans_entry, dict) else (ans_entry if ans_entry else "Unanswered")
        correct_answer = q.get('correct_answer', "Data Missing")
        
        # REPAIR: Bulletproof Scoring Logic (Index-based [0])
        safe_user = str(user_choice).strip().upper()
        safe_correct = str(correct_answer).strip().upper()
        
        # Extract first character for letter-based matching (e.g., 'B' vs 'B. Text')
        user_idx = safe_user[0] if safe_user and safe_user != "UNANSWERED" else "?"
        correct_idx = safe_correct[0] if safe_correct and safe_correct != "DATA MISSING" else "!"
        
        if user_idx == correct_idx and user_idx != "?":
            is_correct = True
            recalculated_score += 1
        else:
            is_correct = False
        
        options_metadata = []
        for idx, opt_text in enumerate(q.get('options', [])):
            label = labels[idx] if idx < len(labels) else str(idx + 1)
            css_class = "secondary"
            icon = ""
            # Highlight Correct Answers: Success for the stored correct one
            if str(opt_text).strip() == str(correct_answer).strip():
                css_class = "success"
                icon = "check"
            # Highlight User's Wrong Choice: Danger for their selection if it didn't match
            elif str(opt_text).strip() == str(user_choice).strip() and not is_correct:
                css_class = "danger"
                icon = "times"
                
            options_metadata.append({
                'label': label,
                'text': opt_text,
                'css_class': css_class,
                'icon': icon
            })

        # AI Review Engine: Prioritize pre-saved explanation
        explanation = q.get('explanation')
        
        if not explanation or not is_correct:
            # Trigger real-time diagnostic if missing or for misses
            prompt = (
                f"The student missed this NEET question: {q.get('question_text')}. "
                f"They chose {user_choice}, but the correct answer is {correct_answer}. "
                "Provide a 2-line explanation based on NCERT."
            )
            try:
                # Use cached or AI-provided if possible, but force for misses for premium polish
                if not explanation:
                    completion = client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=100
                    )
                    explanation = completion.choices[0].message.content.strip()
            except:
                explanation = f"Review NCERT Chapter {test.subject.name if test.subject else 'Biology'} for critical diagnostic context."
        
        processed_results.append({
            'index': i + 1,
            'question_text': q.get('question_text'),
            'is_correct': is_correct,
            'options': options_metadata,
            'explanation': explanation
        })

    context = {
        'test': test,
        'recalculated_score': recalculated_score,
        'results': processed_results,
        'score_percentage': round((recalculated_score / test.total_questions) * 100, 1) if test.total_questions > 0 else 0
    }
    return render(request, 'registration/result_detail.html' if 'registration' in request.path else 'quiz/result.html', context)

@login_required
@require_GET
def student_dashboard_data(request):
    """Aggregates TestResults for the Performance Analytics dashboard."""
    user_results = TestResult.objects.filter(user=request.user) \
        .values('subject__name') \
        .annotate(
            avg_score=Avg('score'),
            total_attempted=Sum('total_questions')
        )

    result_map = {r['subject__name']: r for r in user_results}
    labels = ['Physics', 'Chemistry', 'Biology']
    average_scores = []
    total_attempts = []

    for label in labels:
        if label in result_map:
            average_scores.append(round(result_map[label]['avg_score'] or 0, 2))
            total_attempts.append(result_map[label]['total_attempted'] or 0)
        else:
            average_scores.append(0)
            total_attempts.append(0)

    dataset = {
        "labels": labels,
        "datasets": [
            {
                "label": "Average Score (%)",
                "data": average_scores,
                "backgroundColor": "rgba(15, 23, 42, 0.1)",
                "borderColor": "rgba(15, 23, 42, 1)",
                "borderWidth": 2,
                "fill": true,
                "pointBackgroundColor": "rgba(15, 23, 42, 1)"
            },
            {
                "label": "Total Questions",
                "data": total_attempts,
                "backgroundColor": "rgba(59, 130, 246, 0.1)",
                "borderColor": "rgba(59, 130, 246, 1)",
                "borderWidth": 2,
                "fill": true,
                "pointBackgroundColor": "rgba(59, 130, 246, 1)"
            }
        ]
    }
    return JsonResponse(dataset, status=200)

@csrf_exempt
@login_required
@require_POST
def chatbot_assistant(request):
    """Socratic AI Chatbot utilizing Groq."""
    try:
        data = json.loads(request.body)
        user_prompt = data.get('prompt', '')
        system_msg = "You are a Socratic tutor for NEET/JEE. Use leading questions."
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": user_prompt}],
            temperature=0.6
        )
        return JsonResponse({"reply": completion.choices[0].message.content})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def get_user_rank(user):
    """Calculates user rank based on percentile accuracy."""
    user_results = TestResult.objects.filter(user=user)
    total_tests = user_results.count()
    if total_tests == 0: return "Aspirant"
    
    all_users_stats = TestResult.objects.values('user').annotate(
        user_avg=Avg(ExpressionWrapper(F('score') * 100.0 / F('total_questions'), output_field=FloatField()))
    ).order_by('-user_avg')
    
    user_avg = user_results.aggregate(
        avg=Avg(ExpressionWrapper(F('score') * 100.0 / F('total_questions'), output_field=FloatField()))
    )['avg']
    
    better_than = 0
    total_active_users = all_users_stats.count()
    for stat in all_users_stats:
        if user_avg >= (stat['user_avg'] or 0):
            better_than += 1
    
    percentile = (better_than / total_active_users) * 100
    if percentile >= 95: return "Neurosurgeon"
    elif percentile >= 85: return "Chief Resident"
    elif percentile >= 70: return "Senior Surgeon"
    elif percentile >= 50: return "Medical Officer"
    else: return "Aspirant"

@login_required
def dashboard_view(request):
    """Renders the dashboard UI with stats and recent activity."""
    user_results = TestResult.objects.filter(user=request.user).order_by('-date_taken')
    total_tests = user_results.count()
    
    # Calculate average accuracy
    avg_accuracy = 0
    if total_tests > 0:
        valid_results = user_results.filter(total_questions__gt=0)
        if valid_results.exists():
            total_acc = sum([(r.score / r.total_questions) * 100 for r in valid_results])
            avg_accuracy = round(total_acc / valid_results.count(), 1)

    # Mock Daily Target (3 tests/day)
    today = timezone.now().date()
    tests_today = user_results.filter(date_taken__date=today).count()
    daily_target_percent = min(int((tests_today / 3) * 100), 100)

    context = {
        'total_tests': total_tests,
        'avg_accuracy': avg_accuracy,
        'recent_activity': user_results[:5],
        'daily_target_percent': daily_target_percent,
        'tests_today': tests_today,
        'rank': get_user_rank(request.user)
    }
    return render(request, 'quiz/dashboard.html', context)

@login_required
def profile_view(request):
    """Renders the user profile with rank and details."""
    user_results = TestResult.objects.filter(user=request.user)
    total_tests = user_results.count()
    context = {
        'total_tests': total_tests,
        'rank': get_user_rank(request.user),
        'user': request.user
    }
    return render(request, 'quiz/profile.html', context)

@login_required
def quiz_view(request):
    """Renders the searchable chapter selection UI."""
    subjects = Subject.objects.prefetch_related('chapters').all()
    return render(request, 'quiz/quiz.html', {'subjects': subjects})

from django.contrib.auth.views import LoginView

class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    extra_context = {'hide_sidebar': True}
    
    def get_success_url(self):
        if self.request.user.is_staff:
            return '/admin/'
        return super().get_success_url()

def signup_view(request):
    """Student registration with NeetPrime session initialization."""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to NeetPrime! Your diagnostic journey begins.")
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})
