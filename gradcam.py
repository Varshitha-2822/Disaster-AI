import torch
import torch.nn.functional as F
import cv2
import numpy as np
from PIL import Image


class GradCAM:
    def __init__(self, model, target_layer):
        self.model = model
        self.target_layer = target_layer

        self.gradients = None
        self.activations = None

        target_layer.register_backward_hook(self.save_gradients)
        target_layer.register_forward_hook(self.save_activations)

    def save_gradients(self, module, grad_input, grad_output):
        self.gradients = grad_output[0]

    def save_activations(self, module, input, output):
        self.activations = output

    def generate_cam(self, input_tensor, class_idx):
        output = self.model(input_tensor)
        self.model.zero_grad()

        class_score = output[0, class_idx]
        class_score.backward()

        gradients = self.gradients.mean(dim=[0, 2, 3])
        activations = self.activations[0]

        cam = torch.zeros(activations.shape[1:], device=activations.device)
        for i, w in enumerate(gradients):
            cam += w * activations[i]

        cam = torch.relu(cam)
        cam -= cam.min()
        cam /= cam.max()

        return cam.detach().cpu().numpy()