import csv
import json
import logging
import os
from functools import wraps

from appauth.models import *
from django import views
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.template import RequestContext
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from groups.models import *
from multipolls.models import *
from prefpy.egmm_mixpl import *
from prefpy.gmm_mixpl import *
from prefpy.mechanism import *

from ..email import setupEmail
from ..models import *
from ..utils import getAllocMethods, getListPollAlgorithms, getViewPreferences

# logger for cache
logger = logging.getLogger(__name__)
from io import TextIOWrapper

active_polls = []

def block_code_users(redirect_url="/polls/regular_polls/code"):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.session.get("is_code_user"):
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


@block_code_users("/polls/regular_polls/code")
def AddStep1View(request):
    """
    Define the first step in creating poll.
    
    Obtain title, description, type, allowing tie, and image from POST of HTTP request.
    Redirects to add step 1 page if request does not contain POST, go to add step 2 otherwise.
    """
    context = RequestContext(request)
    if request.method == 'POST':
        questionString = request.POST['questionTitle']
        questionDesc = request.POST['desc']
        questionType = request.POST['questiontype']
        imageURL = request.POST['imageURL']
        tie=False
        t = request.POST.getlist('allowties')
        if "1" in t:
            tie = True
        if "2" in t:
            tie = False

        # create a new question using information from the form and inherit
        # settings from the user's preferences
        question = Question(question_text=questionString, question_desc=questionDesc,
                            pub_date=timezone.now(), question_owner=request.user,
                            display_pref=request.user.userprofile.displayPref,
                            emailInvite=request.user.userprofile.emailInvite,
                            emailDelete=request.user.userprofile.emailDelete,
                            emailStart=request.user.userprofile.emailStart,
                            emailStop=request.user.userprofile.emailStop, creator_pref=1,allowties = tie)
        if request.FILES.get('docfile') != None:
            question.image = request.FILES.get('docfile')
        elif imageURL != '':
            question.imageURL = imageURL
        question.question_type = questionType
        
        question.save()
        setupEmail(question)
        return HttpResponseRedirect(reverse('polls:AddStep2', args=(question.id,)))
    return render(request,'polls/add_step1.html', {})


@method_decorator(block_code_users("/polls/regular_polls/code"), name="dispatch")
class AddStep2View(views.generic.DetailView):
    """Define step 2 in creating poll: adding choices."""
    
    model = Question
    template_name = 'polls/add_step2.html'
    def get_context_data(self, **kwargs):
        ctx = super(AddStep2View, self).get_context_data(**kwargs)
        ctx['items'] = self.object.item_set.all()
        return ctx
    def get_queryset(self):
        return Question.objects.filter(pub_date__lte=timezone.now())


@method_decorator(block_code_users("/polls/regular_polls/code"), name="dispatch")
class AddStep3View(views.generic.DetailView):
    """Defind step 3 in creating poll: inviting voters."""

    model = Question
    template_name = 'polls/add_step3.html'

    def getUsersFromLatestCSV(self, recentCSVText, existingUsers):
        registeredUsers, unRegisteredUsers=[],[]
        if(recentCSVText is not None): 
            userIDsFromCSV = recentCSVText.split(",")
            userIDsFromCSV = [userID.strip() for userID in userIDsFromCSV]

            existingUserIDs = [user.username for user in existingUsers]

            for userID in userIDsFromCSV:
                if userID in existingUserIDs:
                    registeredUsers.append(userID)
                else:
                    unRegisteredUsers.append(userID)

        return registeredUsers, unRegisteredUsers

    def get_context_data(self, **kwargs):
        ctx = super(AddStep3View, self).get_context_data(**kwargs)
        ctx['users'] = User.objects.filter(userprofile__is_code_user=False)
        ctx['groups'] = Group.objects.all()
        
        curr_question = ctx['question']
        ctx['recentCSVText'] = curr_question.recentCSVText
        registeredUsers, unRegisteredUsers = self.getUsersFromLatestCSV(curr_question.recentCSVText, ctx['users'])
        ctx['registeredUsers'] = registeredUsers
        ctx['unRegisteredUsers'] = unRegisteredUsers
        ctx['allUsers'] = registeredUsers + unRegisteredUsers  

        if Email.objects.filter(question=self.object).count() > 0:
            ctx['emailInvite'] = Email.objects.filter(question=self.object, type=1)[0]
            ctx['emailDelete'] = Email.objects.filter(question=self.object, type=2)[0]
            ctx['emailStart'] = Email.objects.filter(question=self.object, type=3)[0]
            ctx['emailStop'] = Email.objects.filter(question=self.object, type=4)[0]
            ctx['emailInviteCSV'] = Email.objects.filter(question=self.object, type=4)[0]
            if len(Email.objects.filter(question=self.object, type=5)) > 0:
                ctx['emailInviteCSV'] = Email.objects.filter(question=self.object, type=5)[0]

        return ctx
    def get_queryset(self):
        return Question.objects.filter(pub_date__lte=timezone.now())


@method_decorator(block_code_users("/polls/regular_polls/code"), name="dispatch")
class AddStep4View(views.generic.DetailView):
    """Define step 4 in creating poll: privacy setting, voting mechanisms, voting UIs, etc."""
    
    model = Question
    template_name = 'polls/add_step4.html'
    def get_context_data(self, **kwargs):
        ctx = super(AddStep4View, self).get_context_data(**kwargs)
        ctx['question'].display_pref = self.request.user.userprofile.displayPref
        ctx['question'].display_user_info = self.request.user.userprofile.display_user_info

        ctx['preference'] = self.request.user.userprofile.displayPref
        ctx['poll_algorithms'] = getListPollAlgorithms()
        ctx['alloc_methods'] = getAllocMethods()
        ctx['view_preferences'] = getViewPreferences()
        ctx['twos'] = [2 ** i for i in range(max(len(ctx['poll_algorithms']), len(ctx['alloc_methods'])))]
        return ctx
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())


def addChoice(request, question_id):
    """
    Called when the "+" for adding choice is pressed.
    
    Submitted data must satisfy:
        - cannot be empty
        - cannot contain exactly same text as choices already added
    Image is optional.
    """

    question = get_object_or_404(Question, pk=question_id)
    item_text = request.POST['choice']
    imageURL = request.POST['imageURL']

    # check for empty strings
    if item_text == "":
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    # check for duplicates
    allChoices = question.item_set.all()
    for choice in allChoices:
        if item_text == choice.item_text:
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    
    # for cases of adding new alternative when poll is paused
    recentlyAdded = False
    if question.status == 4:
        recentlyAdded = True
    # create the choice
    item = Item(question=question, item_text=item_text, timestamp=timezone.now(),
                recently_added=recentlyAdded)

    # if the user uploaded an image or set a URL, add it to the item
    if request.FILES.get('docfile') != None:
        item.image = request.FILES.get('docfile')
    elif imageURL != '':
        item.imageURL = imageURL
    
    # save the choice
    item.save()
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def editChoice(request, question_id):
    """Called when choice title or description is edited in poll info page."""
    
    question = get_object_or_404(Question, pk=question_id)
    for item in question.item_set.all():
        # get data from POST request
        new_text = request.POST["item"+str(item.id)]
        item_desc = request.POST["itemdescription"+str(item.id)]
        imageURL = request.POST["imageURL"+str(item.id)]
        # update choice info accordingly
        if item_desc != "":
            item.item_description = item_desc
        if request.FILES.get("docfile"+str(item.id)) != None:
            item.image = request.FILES.get("docfile"+str(item.id))
        elif imageURL != "":
            item.imageURL = imageURL
        item.item_text = new_text
        item.save()
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def editBasicInfo(request, question_id):
    """
    Called in basic info tab in poll info page when saving changes.
    
    Updates title, description, available voting UIs, and whether ties are allowed.
    """
    
    question = get_object_or_404(Question, pk=question_id)
    # update title and description
    new_title = question.question_text
    if "title" in request.POST:
        new_title = request.POST["title"]
    new_desc = question.question_desc
    if "desc" in request.POST:
        new_desc = request.POST["desc"]
    question.question_text = new_title
    question.question_desc = new_desc
    
    # update UIs
    twocol = False
    onecol = False
    slider = False
    star = False
    yesno = False
    yesno2 = False
    BUI_slider = False
    LUI = False
    IBUI = False
    uilist = request.POST.getlist('ui')
    if "twocol" in uilist:
        twocol = True
    if "onecol" in uilist:
        onecol = True
    if "slider" in uilist:
        slider = True
    if "star" in uilist:
        star = True
    if "yesno" in uilist:
        yesno = True
    if "yesno2" in uilist:
        yesno2 = True
    if "BUI_slider" in uilist:
        BUI_slider = True 
    if "LUI" in uilist:
        LUI = True
    if "IBUI" in uilist:
        IBUI = True
    question.twocol_enabled = twocol
    question.onecol_enabled = onecol
    question.slider_enabled = slider
    question.star_enabled = star
    question.yesno_enabled = yesno
    question.yesno2_enabled = yesno2
    question.budgetUI_enabled = BUI_slider
    question.ListUI_enabled =LUI
    question.infiniteBudgetUI_enabled =IBUI
    question.ui_number = twocol+onecol+slider+star+yesno+yesno2+BUI_slider+LUI+IBUI
    
    # update whether ties are allowed
    tie=question.allowties
    t = request.POST.getlist('allowties')
    if "1" in t:
        tie = True
    if "2" in t:
        tie = False

    question.allowties = tie
    
    # save the changes
    question.save()
    request.session['setting'] = 8
    messages.success(request, "Your changes have been saved.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def deleteChoice(request, choice_id):
    """Delete a choice; can only be done before a poll starts."""
    
    item = get_object_or_404(Item, pk=choice_id)
    item.delete()
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def addFolder(request):
    if request.method == 'POST':
        title = request.POST['title']
        fold = Folder(user=request.user, title=title, edit_date=timezone.now())
        fold.save()
        for poll in request.POST.getlist('polls'):
            try:
                q = Question.objects.filter(id=int(poll)).all()[0]
                fold.questions.add(q)
            except:
                print("Error: poll not working")
        fold.save()
        # print(fold.questions)
        return HttpResponseRedirect(reverse('polls:regular_polls'))
    else:
        print("Error: not post in addFolder function line 1993")


def deleteFolder(request, folder_id):
    try:
        folder_obj = get_object_or_404(Folder, pk=folder_id)
        folder_obj.delete()
    except:
        print("Problem in retrieving Folder object with id:" ,folder_id)
    return HttpResponseRedirect(reverse('polls:regular_polls'))


def upload_csv_choices(request, question_id):
    """
    Handle CSV file upload to add multiple alternatives at once.
    Expected CSV format:
    - One row per item
    - First column: Item name (required)
    - Second column: Item description (optional)
    - Third column: Asset name (optional)
    - Additional columns are ignored
    
    """
    question = get_object_or_404(Question, pk=question_id)
    
    # check if user is poll owner
    if request.user != question.question_owner:
        messages.error(request, "Only the poll owner can add alternatives.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    
    if request.method == 'POST' and request.FILES.get('csvFile'):
        csv_file = request.FILES['csvFile']
        
        # validate file type
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Please upload a CSV file.")
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
        
        try:
            # read CSV file
            csv_text = TextIOWrapper(csv_file.file, encoding='utf-8')
            csv_reader = csv.reader(csv_text)
            
            # Check if first row is a header
            # Get the first row to inspect
            first_row = next(csv_reader, None)
            
            # If no rows, exit early
            if not first_row:
                messages.error(request, "The CSV file is empty.")
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            
            # Check if first row contains common header terms
            header_indicators = ['course', 'name', 'description', 'image', 'reference', 'title', 'alternative']
            first_cell_lower = first_row[0].lower().strip()
            is_header = any(indicator in first_cell_lower for indicator in header_indicators)
            
            # If it's not a header, we need to process it as a data row
            rows_to_process = [first_row] if not is_header else []
            
            items_added = 0
            items_skipped = 0
            items_with_desc = 0
            items_with_images = 0
            
            # Process the first row if it wasn't a header
            for row in rows_to_process:
                if row and row[0].strip():
                    item_name = row[0].strip()
                    item_description = row[1].strip() if len(row) > 1 and row[1].strip() else "No description"
                    item_reference = row[2].strip() if len(row) > 2 and row[2].strip() else ""
                    
                    # check duplicates
                    if not question.item_set.filter(item_text=item_name).exists():
                        # create new item
                        recentlyAdded = question.status == 4
                        item = Item(
                            question=question,
                            item_text=item_name,
                            item_description=item_description,
                            imageReference=item_reference,
                            timestamp=timezone.now(),
                            recently_added=recentlyAdded
                        )
                        item.save()
                        items_added += 1
                        if item_description:
                            items_with_desc += 1
                        if item_reference:
                            items_with_images += 1
                    else:
                        items_skipped += 1
            
            # Process the remaining rows
            for row in csv_reader:
                if not row or not row[0].strip():  # skip empty rows or rows without name
                    continue
                    
                item_name = row[0].strip()
                item_description = row[1].strip() if len(row) > 1 and row[1].strip() else "No description"
                item_reference = row[2].strip() if len(row) > 2 and row[2].strip() else ""
                
                # check duplicates
                if question.item_set.filter(item_text=item_name).exists():
                    items_skipped += 1
                    continue
                
                # create new item
                recentlyAdded = question.status == 4
                item = Item(
                    question=question,
                    item_text=item_name,
                    item_description=item_description,
                    imageReference=item_reference,
                    timestamp=timezone.now(),
                    recently_added=recentlyAdded
                )
                item.save()
                items_added += 1
                if item_description:
                    items_with_desc += 1
                if item_reference:
                    items_with_images += 1
            
            # provide feedback
            if is_header:
                messages.info(request, "Detected and skipped header row.")
                
            if items_added > 0:
                success_msg = f"Successfully added {items_added} items"
                details = []
                if items_with_desc > 0:
                    details.append(f"{items_with_desc} with descriptions")
                if items_with_images > 0:
                    details.append(f"{items_with_images} with image references")
                if details:
                    success_msg += f" ({', '.join(details)})"
                messages.success(request, success_msg + ".")
            if items_skipped > 0:
                messages.warning(request, f"Skipped {items_skipped} duplicate items.")
                
        except Exception as e:
            messages.error(request, f"Error processing CSV file: {str(e)}")
    
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def upload_bulk_images(request, question_id):
    """
    Handle bulk image upload to match with existing items.
    Images will be attached to items that have a matching reference in their imageReference field.
    """
    question = get_object_or_404(Question, pk=question_id)
    
    # if user is poll owner
    if request.user != question.question_owner:
        messages.error(request, "Only the poll owner can add alternatives.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    
    if request.method == 'POST' and request.FILES.getlist('imageFiles'):
        try:
            image_files = request.FILES.getlist('imageFiles')
            
            images_matched = 0
            images_unmatched = 0
            
            # Get all items for this question
            all_items = question.item_set.all()
            
            for image_file in image_files:
                # Try to find items with matching imageReference
                matching_items = all_items.filter(imageReference=image_file.name)
                
                if matching_items.exists():
                    # Update all matching items with the actual image file
                    for item in matching_items:
                        item.image = image_file
                        item.save()
                        images_matched += 1
                else:
                    # Try with just the filename without extension as fallback
                    base_name = os.path.splitext(image_file.name)[0]
                    matching_items = all_items.filter(imageReference=base_name)
                    
                    if matching_items.exists():
                        for item in matching_items:
                            item.image = image_file
                            item.save()
                            images_matched += 1
                    else:
                        images_unmatched += 1
            
            if images_matched > 0:
                messages.success(request, f"Successfully attached {images_matched} images to existing items.")
            if images_unmatched > 0:
                messages.warning(request, f"Could not match {images_unmatched} images to any existing items.")
                
        except Exception as e:
            messages.error(request, f"Error processing image files: {str(e)}")
    
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def upload_single_image(request, question_id):
    """
    Handle single image upload for an existing item.
    Updates the image for an existing item instead of creating a new one.
    """
    question = get_object_or_404(Question, pk=question_id)
    
    # if user is poll owner
    if request.user != question.question_owner:
        messages.error(request, "Only the poll owner can modify items.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    
    if request.method == 'POST' and 'image' in request.FILES:
        try:
            image_file = request.FILES['image']
            item_id = request.POST.get('item_id', None)
            
            if not item_id:
                messages.error(request, "No item selected. Please select an item to update.")
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            
            # Get the item to update
            try:
                item = Item.objects.get(pk=item_id, question=question)
                
                # Remove any existing image (optional)
                if item.image:
                    try:
                        old_image_path = item.image.path
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                    except:
                        pass  # Ignore errors in removing old image
                
                # Update the image
                item.image = image_file
                item.save()
                
                messages.success(request, f"Successfully updated image for '{item.item_text}'.")
            except Item.DoesNotExist:
                messages.error(request, "The specified item was not found.")
                
        except Exception as e:
            messages.error(request, f"Error processing image file: {str(e)}")
    
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def delete_items(request, question_id):
    """Delete multiple items or all items from a poll."""
    question = get_object_or_404(Question, pk=question_id)
    
    # check if user is poll owner
    if request.user != question.question_owner:
        messages.error(request, "Only the poll owner can delete alternatives.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    
    if request.method == 'POST':
        if 'delete_all' in request.POST:
            # delete all 
            question.item_set.all().delete()
            messages.success(request, "All items have been deleted.")
        else:
            # delete selected 
            try:
                item_ids = json.loads(request.POST.get('item_ids', '[]'))
                question.item_set.filter(id__in=item_ids).delete()
                messages.success(request, f"{len(item_ids)} items have been deleted.")
            except Exception as e:
                messages.error(request, f"Error deleting items: {str(e)}")
    
    request.session['setting'] = 0

    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
