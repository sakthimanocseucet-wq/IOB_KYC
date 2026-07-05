"""
MiniFASNet V2 Architecture (PyTorch) — matches 2.7_80x80_MiniFASNetV2.pth checkpoint.

Architecture from Silent-Face-Anti-Spoofing (minivision-ai).
State dict keys have 'module.' prefix from DataParallel — strip on load.
"""

import torch
import torch.nn as nn


class _ConvBNPReLU(nn.Module):
    def __init__(self, in_c, out_c, kernel, stride=1, padding=0, groups=1):
        super().__init__()
        self.conv = nn.Conv2d(in_c, out_c, kernel, stride, padding, groups=groups, bias=False)
        self.bn = nn.BatchNorm2d(out_c)
        self.prelu = nn.PReLU(out_c)

    def forward(self, x):
        return self.prelu(self.bn(self.conv(x)))


class _ConvBN(nn.Module):
    def __init__(self, in_c, out_c, kernel, stride=1, padding=0, groups=1):
        super().__init__()
        self.conv = nn.Conv2d(in_c, out_c, kernel, stride, padding, groups=groups, bias=False)
        self.bn = nn.BatchNorm2d(out_c)

    def forward(self, x):
        return self.bn(self.conv(x))


class InvertedResidual(nn.Module):
    """Inverted bottleneck: conv -> depthwise -> project, with optional residual."""
    def __init__(self, in_c, mid_c, out_c):
        super().__init__()
        self.conv = _ConvBNPReLU(in_c, mid_c, 1)
        self.conv_dw = _ConvBNPReLU(mid_c, mid_c, 3, stride=1, padding=1, groups=mid_c)
        self.project = _ConvBN(mid_c, out_c, 1)
        self.use_res = (in_c == out_c)

    def forward(self, x):
        out = self.conv(x)
        out = self.conv_dw(out)
        out = self.project(out)
        return x + out if self.use_res else out


class _InvertedResidualBlock(nn.Module):
    """Wraps InvertedResidual in a `.model` list to match checkpoint key naming."""
    def __init__(self, blocks):
        super().__init__()
        self.model = nn.ModuleList(blocks)


class MiniFASNetV2(nn.Module):
    def __init__(self, embedding_size=128, conv6_kernel=(7, 7), drop_p=0.2, num_classes=3, img_channel=3):
        super().__init__()

        # conv1: 3 -> 32, stride 2
        self.conv1 = _ConvBNPReLU(img_channel, 32, 3, stride=2, padding=1)

        # conv2_dw: depthwise 32 -> 32
        self.conv2_dw = _ConvBNPReLU(32, 32, 3, stride=1, padding=1, groups=32)

        # conv_23: inverted bottleneck 32 -> 103(mid) -> 64
        self.conv_23 = InvertedResidual(32, 103, 64)

        # conv_3: 4 residual blocks wrapped in .model
        self.conv_3 = _InvertedResidualBlock([
            InvertedResidual(64, 13, 64) for _ in range(4)
        ])

        # conv_34: inverted bottleneck 64 -> 231(mid) -> 128
        self.conv_34 = InvertedResidual(64, 231, 128)

        # conv_4: 6 residual blocks
        conv4_mids = [231, 52, 26, 77, 26, 26]
        self.conv_4 = _InvertedResidualBlock([
            InvertedResidual(128, m, 128) for m in conv4_mids
        ])

        # conv_45: inverted bottleneck 128 -> 308(mid) -> 128
        self.conv_45 = InvertedResidual(128, 308, 128)

        # conv_5: 2 residual blocks
        self.conv_5 = _InvertedResidualBlock([
            InvertedResidual(128, 26, 128) for _ in range(2)
        ])

        # conv_6_sep: pointwise 128 -> 512
        self.conv_6_sep = _ConvBNPReLU(128, 512, 1)

        # conv_6_dw: depthwise 512 -> 512, kernel 5x5
        self.conv_6_dw = _ConvBN(512, 512, 5, stride=1, padding=2, groups=512)

        # Global average pooling
        self.gap = nn.AdaptiveAvgPool2d(1)

        # FC layers
        self.linear = nn.Linear(512, embedding_size)
        self.bn = nn.BatchNorm1d(embedding_size)
        self.prob = nn.Linear(embedding_size, num_classes)

    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2_dw(x)
        x = self.conv_23(x)
        for block in self.conv_3.model:
            x = block(x)
        x = self.conv_34(x)
        for block in self.conv_4.model:
            x = block(x)
        x = self.conv_45(x)
        for block in self.conv_5.model:
            x = block(x)
        x = self.conv_6_sep(x)
        x = self.conv_6_dw(x)
        x = self.gap(x)
        x = x.view(x.size(0), -1)
        x = self.linear(x)
        x = self.bn(x)
        out = self.prob(x)
        return out
