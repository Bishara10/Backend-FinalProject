from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pathlib import Path
import cv2
import numpy as np
import librosa 
import os
import parselmouth
import soundfile as sf
from parselmouth.praat import call
import tensorflow as tf
from tensorflow.keras.layers import Input, Dense, Flatten, Conv1D, MaxPooling1D, Concatenate, Reshape
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam


### MODEL ###

eye_tracking_input_shape = (3,)  # 3 values per sample: mean, median, std
reaction_time_input_shape_1 = (3,)
reaction_time_input_shape_2 = (3,)
audio_input_shape = (5,)  # 5 features: Fundamental Frequency, Jitter, Shimmer, Harmonics-to-noise ratio, Voice quality index
questionnaire_input_shape = (20,)  # 20 questions in total

# Eye tracking model
eye_tracking_input = Input(shape=eye_tracking_input_shape, name='eye_tracking_input')
x_eye = Dense(64, activation='relu')(eye_tracking_input)

# Reaction time models
reaction_time_input_1 = Input(shape=reaction_time_input_shape_1, name='reaction_time_input_1')
reaction_time_input_2 = Input(shape=reaction_time_input_shape_2, name='reaction_time_input_2')
x_reaction_time_1 = Dense(64, activation='relu')(reaction_time_input_1)
x_reaction_time_2 = Dense(64, activation='relu')(reaction_time_input_2)

# Audio recording model
audio_input = Input(shape=audio_input_shape, name='audio_input')
x_audio = Dense(64, activation='relu')(audio_input)
x_audio = Dense(32, activation='relu')(x_audio)

# Questionnaire model
questionnaire_input = Input(shape=questionnaire_input_shape, name='questionnaire_input')
x_questionnaire = Dense(64, activation='relu')(questionnaire_input)
x_questionnaire = Dense(32, activation='relu')(x_questionnaire)

# Concatenate all models
concatenated = Concatenate()([x_eye, x_reaction_time_1, x_reaction_time_2, x_audio, x_questionnaire])
x = Dense(64, activation='relu')(concatenated)
x = Dense(32, activation='relu')(x)
output = Dense(4, activation='softmax', name='output')(x)

# Create model
model_pred = Model(inputs=[eye_tracking_input, reaction_time_input_1, reaction_time_input_2, audio_input, questionnaire_input], outputs=output)

# Compile model
model_pred.compile(optimizer=Adam(learning_rate=0.001), loss='categorical_crossentropy', metrics=['accuracy'])

weight_path = Path('ADHD/static/weights/model_weights (1).h5')

# To load the weights later
model_pred.load_weights(weight_path)
model_pred.summary()

# Create your views here.

def instructions(request):
    template = loader.get_template('instructions.html')
    return HttpResponse(template.render())

def eyeTest(request):
    template = loader.get_template('eye-test.html')
    return HttpResponse(template.render())

def vocalTest(request):
    template = loader.get_template('vocal-test.html')
    return HttpResponse(template.render())

def questionnaire(request):
    template = loader.get_template('questionnaire-styled.html')
    return HttpResponse(template.render())


def landingPage(request):
    template = loader.get_template('nodus.html')
    return HttpResponse(template.render())

def FAQ(request):
    template = loader.get_template('FAQ.html')
    return HttpResponse(template.render())

@csrf_exempt
def processing(request):
    template = loader.get_template('processing.html')
    return HttpResponse(template.render())

def clean(request):

    try:
        save_path_initial = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_initial-video.webm" )
        save_path_eye = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_recorded-video.webm" )
        save_path_vocal = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_audio-recording.mp3" )
        save_path_questionnaire = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_questionnaire.txt" )
        save_path_reaction = Path('ADHD/temporary_files/'  + str( request.META['REMOTE_ADDR'])+ "_reaction-time-arrays.txt")
        
        os.remove(save_path_eye)
        os.remove(save_path_vocal)
        os.remove(save_path_questionnaire)
        os.remove(save_path_reaction)
        os.remove(save_path_initial)
        return JsonResponse({'message': 'Files deleted'}, status=200)  
    except: 
        return JsonResponse({'message': 'Error - could not delete files'}, status=201)  

@csrf_exempt
def results(request):
    template = loader.get_template('test-results.html')

    # Feed data to DL model and retrieve the probabilities
    ip = request.META['REMOTE_ADDR'] # Extract IP to conduct analysis on files with this IP
    save_path_eye = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_recorded-video.webm" )
    save_path_vocal = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_audio-recording.mp3" )
    save_path_questionnaire = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_questionnaire.txt" )
    save_path_reaction = Path('ADHD/temporary_files/'  + str( request.META['REMOTE_ADDR'])+ "_reaction-time-arrays.txt")
    
    questionnaire = ''
    reaction = ""
    reaction_time_base = ''
    reaction_time_dist = ''


    #try:
    voice_analysis = analyze_voice(save_path_vocal)
    #except:
     #   return JsonResponse({'message': 'Error - could not analyze voice'}, status=201)
    
    try:
        eye_analysis = eye_test_analysis(save_path_eye)
    except:
        return JsonResponse({'message': 'Error - could not analyze eye movements'}, status=201)
    
    try:
        with open(save_path_questionnaire, 'r') as f:
            questionnaire += f.read()
    except:
        return JsonResponse({'message': 'Error - could not access questionnaire answers'}, status=201)
    
    try:
        with open(save_path_reaction, 'r') as f:
            reaction += f.read()
    except:
        return JsonResponse({'message': 'Error - could not access reaction time data'}, status=201)
    
    reaction_time_base, reaction_time_dist = reaction.split("\n")

    reaction_time_base = reaction_time_base[1:]
    reaction_time_base = reaction_time_base[:-1]
    base_array = reaction_time_base.split(',')
    base_array = [int(i) for i in base_array]

    reaction_time_dist = reaction_time_dist[1:]
    reaction_time_dist = reaction_time_dist[:-1]
    dist_array = reaction_time_dist.split(',')
    dist_array = [int(i) for i in dist_array]

    base, dist = calculate_mean_median_std(base_array), calculate_mean_median_std(dist_array)

    
    if not questionnaire.split(',')[-1].isnumeric():
        data_file_path = Path('ADHD/temporary_files/data.txt')
        with open(data_file_path,'a') as f:

            eye = eye_analysis
            vocal = voice_analysis
            questions = tuple(map(int, questionnaire.split(',')[:-1]))
            reactions_base = base
            reactions_dist = dist

            for i in eye:
                f.write(str(i) + ", ")
            for i in vocal:
                f.write(str(i) + ", ")
            for i in questions:
                f.write(str(i) + ", ")
            for i in reactions_base:
                f.write(str(i) + ", ")
            for i in range(len(reactions_dist)):
                f.write(str(reactions_dist[i]) + ", ")   
            f.write(questionnaire.split(',')[-1] + "\n")
    else:
        questions = tuple(map(int, questionnaire.split(',')))


    percentages = model(eye_analysis, base, dist, voice_analysis, questions)
    tips = get_tips(percentages)
    context = {
        'percentages': percentages,
        'tips': tips,
        'eye_analysis': eye_analysis,
        'vocal_analysis': voice_analysis,
        'questionnaire': questionnaire,
        'reaction_time': reaction.split('\n')
    } 

    return HttpResponse(template.render(context=context))

def get_tips(percentages):
    
    combined = "Balance your day with both physical activities and quieter tasks, using visual schedules and verbal reminders to stay organized. Break tasks into smaller steps and check in with yourself or ask for help to ensure you stay on track. Engage in structured physical activities and plan movement breaks to manage hyperactivity. Use positive reinforcement and behavior plans with specific goals and rewards to encourage good behavior and task completion. Collaborate with teachers and involve your family in supporting you. Enjoy consistent feedback and support from those around you to manage both inattentive and hyperactive symptoms effectively."
    hyperactive = "Incorporate plenty of physical activities and movement breaks into your day to help manage energy. Engage in structured activities with clear rules and fewer choices to maintain focus. Play games that teach self-control, and watch how adults model patience. Use a behavior chart to track and reward positive behaviors like waiting your turn and sitting still during meals. Channel your energy into sports, crafts, and organized play. Remember to take short breaks during tasks that require sitting still. Enjoy consistent and immediate rewards for good behavior to understand what is expected of you."
    inattentive = "Create a consistent daily routine and use visual aids to remember what tasks come next. Break instructions into small, manageable steps, and repeat them back to ensure you understand. Set up a quiet, clutter-free area for focused activities like homework. Celebrate small achievements with immediate praise or rewards to stay motivated. Regularly check in with yourself or ask for help to stay on track. Simplify your environment by minimizing distractions and keeping only necessary items around. Set small, achievable goals and enjoy the satisfaction of completing each step."
    no_adhd = "While ADHD is often a neurodevelopmental disorder present from early childhood, maintaining a healthy lifestyle can support overall brain health and well-being. Establish a consistent daily routine with balanced activities to reduce stress and improve focus. Prioritize a nutritious diet rich in fruits, vegetables, lean proteins, and whole grains, and avoid excessive sugar and processed foods. Ensure you get regular physical exercise, which can enhance brain function and reduce anxiety. Maintain good sleep hygiene by having a consistent bedtime and creating a relaxing sleep environment. Engage in activities that challenge your mind, such as puzzles, reading, and learning new skills. Limit screen time and take regular breaks from electronic devices to prevent overstimulation. Finally, practice mindfulness and relaxation techniques like deep breathing or meditation to manage stress and improve concentration."

    tips_array = [combined, hyperactive, inattentive, no_adhd]

    return tips_array[np.argmax(percentages)]

@csrf_exempt
def upload_video(request):
    if request.method == 'POST' and request.FILES.get('initial-video'):
        video = request.FILES['initial-video']
        save_path = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_" + video.name )
        with open(save_path, 'wb+') as destination:
            for chunk in video.chunks():
                destination.write(chunk)
        
        res = initial_video_check(save_path)
        if(res):
            return JsonResponse({'message': 'Confiuguration complete'}, status=200)
        else:
            return JsonResponse({'message': 'No eyes detected, try sitting closer to the screen, brighten or dampen the room'}, status=201)
        
    elif request.method == 'POST' and request.FILES.get('recorded-video'):
        video = request.FILES['recorded-video']
        base_reaction_time = request.POST['reactionTimeBase']
        dis_reaction_time = request.POST['reactionTimeDistractors']
        save_path = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_" + video.name )
        with open(save_path, 'wb+') as destination:
            for chunk in video.chunks():
                destination.write(chunk)
        save_path_arrays = Path('ADHD/temporary_files/'  + str( request.META['REMOTE_ADDR'])+ "_reaction-time-arrays.txt")
        with open(save_path_arrays, 'w+') as destination:
            destination.write(base_reaction_time)
            destination.write('\n')
            destination.write(dis_reaction_time)

        res = True
        if(res):
            return JsonResponse({'message': str(res)}, status=200)
        else:
            return JsonResponse({'message': 'No eyes detected, try sitting closer to the screen, brighten or dampen the room'}, status=201)

    return JsonResponse({'error': 'Invalid request'}, status=400)

def initial_video_check(url):
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')

    cap = cv2.VideoCapture(url)
    detected = 0
    undetected = 0

    while True:
        ret, frame = cap.read()
        if ret is False:
            break
        faces = face_cascade.detectMultiScale(frame, 1.3, 5)
        if len(faces) != 0:
            for (x,y,w,h) in faces:
                face_center = [int(h/2),int(w/2)]
                roi_color = frame[y:y+h, x:x+w]
                eyes = eye_cascade.detectMultiScale(roi_color)
                if len(eyes) != 0:
                    detected += 1
                else:
                    undetected += 1
        else:
            undetected += 1

    cap.release()
    return detected > undetected*1.5 and detected > 40

def eye_test_analysis(url):
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')

    initial_coords_left = [-1,-1]
    initial_coords_right = [-1,-1]
    face_center = [-1,-1]
    eye_coordinates = [-1,-1]

    cap = cv2.VideoCapture(url)
    left_eye_coordinates_array = []
    right_eye_coordinates_array = []
    while True:
        ret, frame = cap.read()
        if ret is False:
            break
        faces = face_cascade.detectMultiScale(frame, 1.3, 5)
        for (x,y,w,h) in faces:
            face_center = [int(h/2),int(w/2)]
            roi_color = frame[y:y+h, x:x+w]
            eyes = eye_cascade.detectMultiScale(roi_color)
            for (ex,ey,ew,eh) in eyes:
                cv2.rectangle(roi_color,(ex,ey),(ex+ew,ey+eh),(0,255,0),2)
                roi = roi_color[ey:ey+eh, ex:ex+ew]
                # Left eye
                if ex < face_center[1]:
                    if initial_coords_left == [-1,-1]:
                        initial_coords_left = [ey + int(eh/2), ex + int(ew/2)]
                # Right eye
                else:
                    if initial_coords_right == [-1,-1]:
                        initial_coords_right = [ey + int(eh/2), ex + int(ew/2)]
                eye_coordinates = [ey + int(eh/2), ex + int(ew/2)]
        try:
            rows, cols, _ = roi.shape
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            gray_roi = cv2.GaussianBlur(gray_roi, (7, 7), 0)
            _, threshold = cv2.threshold(gray_roi, 115, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(threshold, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=lambda x: cv2.contourArea(x), reverse=True)
            for cnt in contours:
                (x, y, w, h) = cv2.boundingRect(cnt)
                #cv2.drawContours(roi, [cnt], -1, (0, 0, 255), 3)
                break
            # Left eye
            if eye_coordinates[1] < face_center[1]:
                if len(left_eye_coordinates_array) == 0:
                    left_eye_coordinates_array.append(((initial_coords_left[1] - eye_coordinates[1]), (initial_coords_left[0] - eye_coordinates[0])))
                elif left_eye_coordinates_array[-1] != ((initial_coords_left[1] - eye_coordinates[1]), (initial_coords_left[0] - eye_coordinates[0])):
                    left_eye_coordinates_array.append(((initial_coords_left[1] - eye_coordinates[1]), (initial_coords_left[0] - eye_coordinates[0])))
            else:
                if len(right_eye_coordinates_array) == 0:
                    right_eye_coordinates_array.append(((initial_coords_left[1] - eye_coordinates[1]), (initial_coords_left[0] - eye_coordinates[0])))
                elif right_eye_coordinates_array[-1] != ((initial_coords_left[1] - eye_coordinates[1]), (initial_coords_left[0] - eye_coordinates[0])):
                    right_eye_coordinates_array.append(((initial_coords_left[1] - eye_coordinates[1]), (initial_coords_left[0] - eye_coordinates[0])))
        except:
            pass

    cap.release()
    difference_right = calculate_difference(right_eye_coordinates_array)
    difference_left = calculate_difference(left_eye_coordinates_array)
    mean_right, median_right, std_right = calculate_mean_median_std(difference_right)
    mean_left, median_left, std_left = calculate_mean_median_std(difference_left)
    mean = (mean_right + mean_left)/2
    median = (median_right + median_left)/2
    std = (std_right + std_left)/2
    return mean, median, std

def calculate_difference(eye_position_array):
    difference = []
    for i in range(1,len(eye_position_array)):
        difference.append(distance_squared(eye_position_array[i-1], eye_position_array[i]))
    return difference

def distance_squared(point1, point2):
    return ((point1[0]-point2[0])**2 + (point1[1] - point2[1])**2)

def calculate_mean_median_std(eye_movement_distance_array):
    data = []
    for coord in eye_movement_distance_array:
        data.append(coord)
    return np.mean(data), np.median(data), np.std(data)

@csrf_exempt
def upload_voice(request):
    if request.method == 'POST' and request.FILES.get('audio-recording'):
        audio = request.FILES['audio-recording']
        save_path = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_" + audio.name )
        with open(save_path, 'wb+') as destination:
            for chunk in audio.chunks():
                destination.write(chunk)
        y, sr = librosa.load(save_path)
        sf.write(save_path, y, sr)
    return JsonResponse({'message': 'Uploaded video successfully'}, status=200)


def analyze_voice(url):

    #y, sr = librosa.load(url, sr=None)
    
    # Extract Fundamental Frequency (F0)
    f0 = extract_fundamental_frequency(str(url))
    
    # Extract Jitter, Shimmer, and HNR
    jitter, shimmer, hnr = extract_jitter_shimmer_hnr(str(url))
    
    # Voice Quality Index (VQI) - example of composite metric
    vqi = (f0 / 100) + jitter + shimmer + (hnr / 10)
    return f0, jitter, shimmer, hnr, vqi

@csrf_exempt
def upload_answers(request):
    if request.method == 'POST' and request.POST.get('questionnaire'): 
        answers = request.POST['questionnaire']
        save_path_arrays = Path('ADHD/temporary_files/' + str( request.META['REMOTE_ADDR'])+ "_questionnaire.txt")
        with open(save_path_arrays, 'w+') as destination:
            destination.write(answers)
    return JsonResponse({'message': "Questionnaire answers uploaded successfully"}, status=200)


def extract_fundamental_frequency(audio_path):
    snd = parselmouth.Sound(audio_path)
    pitch = call(snd, "To Pitch", 0.0, 75, 600)
    mean_f0 = call(pitch, "Get mean", 0, 0, "Hertz")
    return mean_f0

def extract_jitter_shimmer_hnr(audio_path):
    snd = parselmouth.Sound(audio_path)
    point_process = call(snd, "To PointProcess (periodic, cc)", 75, 600)
    
    # Jitter (local)
    jitter = call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
    
    # Shimmer (local)
    shimmer = call([snd, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
    
    # Harmonics-to-Noise Ratio (HNR)
    harmonicity = call(snd, "To Harmonicity (cc)", 0.01, 75, 0.01, 1.0)
    hnr = call(harmonicity, "Get mean", 0, 0)
    
    return jitter, shimmer, hnr

# Receive tuples and turn them into lists, then into np.arrays
def model(eye, react1, react2, vocal, questions):

    eye_list = list(eye)
    react1_list = list(react1)
    react2_list = list(react2)
    vocal_list = list(vocal)
    questions_list = list(questions)

    eye_np = np.array([eye_list])
    react1_np = np.array([react1_list])
    react2_np = np.array([react2_list])
    vocal_np = np.array([vocal_list])
    questions_np = np.array([questions_list])

    prediction = model_pred.predict([eye_np, react1_np, react2_np, vocal_np, questions_np])
    return prediction[0]
