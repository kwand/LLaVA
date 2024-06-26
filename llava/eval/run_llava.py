import torch

from llava.constants import (
    IMAGE_TOKEN_INDEX,
    DEFAULT_IMAGE_TOKEN,
    DEFAULT_IM_START_TOKEN,
    DEFAULT_IM_END_TOKEN,
    IMAGE_PLACEHOLDER,
)
from llava.conversation import conv_templates, SeparatorStyle
from llava.model.builder import load_pretrained_model
from llava.utils import disable_torch_init
from llava.mm_utils import (
    process_images,
    tokenizer_image_token,
    get_model_name_from_path,
)

from PIL import Image

import requests
from PIL import Image
from io import BytesIO
import re

import dataclasses
import simple_parsing


def image_parser(args):
    out = args.image_file.split(args.sep)
    return out


def load_image(image_file):
    if image_file.startswith("http") or image_file.startswith("https"):
        response = requests.get(image_file)
        image = Image.open(BytesIO(response.content)).convert("RGB")
    else:
        image = Image.open(image_file).convert("RGB")
    return image


def load_images(image_files):
    out = []
    for image_file in image_files:
        image = load_image(image_file)
        out.append(image)
    return out


def eval_model(args):
    # Model
    disable_torch_init()

    model_name = get_model_name_from_path(args.model_path)
    tokenizer, model, image_processor, context_len = load_pretrained_model(
        args.model_path, args.model_base, model_name
    )

    qs = args.query
    image_token_se = DEFAULT_IM_START_TOKEN + DEFAULT_IMAGE_TOKEN + DEFAULT_IM_END_TOKEN
    if IMAGE_PLACEHOLDER in qs:
        if model.config.mm_use_im_start_end:
            qs = re.sub(IMAGE_PLACEHOLDER, image_token_se, qs)
        else:
            qs = re.sub(IMAGE_PLACEHOLDER, DEFAULT_IMAGE_TOKEN, qs)
    else:
        if model.config.mm_use_im_start_end:
            qs = image_token_se + "\n" + qs
        else:
            qs = DEFAULT_IMAGE_TOKEN + "\n" + qs

    if "llama-2" in model_name.lower():
        conv_mode = "llava_llama_2"
    elif "mistral" in model_name.lower():
        conv_mode = "mistral_instruct"
    elif "v1.6-34b" in model_name.lower():
        conv_mode = "chatml_direct"
    elif "v1" in model_name.lower():
        conv_mode = "llava_v1"
    elif "mpt" in model_name.lower():
        conv_mode = "mpt"
    else:
        conv_mode = "llava_v0"

    if args.conv_mode is not None and conv_mode != args.conv_mode:
        print(
            "[WARNING] the auto inferred conversation mode is {}, while `--conv-mode` is {}, using {}".format(
                conv_mode, args.conv_mode, args.conv_mode
            )
        )
    else:
        args.conv_mode = conv_mode

    conv = conv_templates[args.conv_mode].copy()
    conv.append_message(conv.roles[0], qs)
    conv.append_message(conv.roles[1], None)
    prompt = conv.get_prompt()

    image_files = image_parser(args)
    images = load_images(image_files)
    image_sizes = [x.size for x in images]
    images_tensor = process_images(
        images,
        image_processor,
        model.config
    ).to(model.device, dtype=torch.float16)

    input_ids = (
        tokenizer_image_token(prompt, tokenizer, IMAGE_TOKEN_INDEX, return_tensors="pt")
        .unsqueeze(0)
        .cuda()
    )

    with torch.inference_mode():
        output_ids = model.generate(
            input_ids,
            images=images_tensor,
            image_sizes=image_sizes,
            do_sample=True if args.temperature > 0 else False,
            temperature=args.temperature,
            top_p=args.top_p,
            num_beams=args.num_beams,
            max_new_tokens=args.max_new_tokens,
            use_cache=True,
        )

    outputs = tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0].strip()
    print(outputs)
@dataclasses.dataclass
class LlavaRunConfig:
    image_file: str
    query: str
    model_path: str = "facebook/opt-350m"
    model_base: str = None
    conv_mode: str = None
    sep: str = ","
    temperature: float = 0.2
    top_p: float = None
    num_beams: int = 1
    max_new_tokens: int = 512

def eval_model_load_only(run_config: LlavaRunConfig):
    disable_torch_init()

    model_name = get_model_name_from_path(run_config.model_path)
    tokenizer, model, image_processor, context_len = load_pretrained_model(
        run_config.model_path, run_config.model_base, model_name
    )

    info_dict = {
        "model_name": model_name,
        "tokenizer": tokenizer,
        "model": model,
        "image_processor": image_processor,
        "context_len": context_len
    }

    return info_dict

def eval_model_prompt_process_only(run_config: LlavaRunConfig, model_info_dict):
    qs = run_config.query
    image_token_se = DEFAULT_IM_START_TOKEN + DEFAULT_IMAGE_TOKEN + DEFAULT_IM_END_TOKEN
    if IMAGE_PLACEHOLDER in qs:
        if model_info_dict["model"].config.mm_use_im_start_end:
            qs = re.sub(IMAGE_PLACEHOLDER, image_token_se, qs)
        else:
            qs = re.sub(IMAGE_PLACEHOLDER, DEFAULT_IMAGE_TOKEN, qs)
    else:
        if model_info_dict["model"].config.mm_use_im_start_end:
            qs = image_token_se + "\n" + qs
        else:
            qs = DEFAULT_IMAGE_TOKEN + "\n" + qs

    if "llama-2" in model_info_dict["model_name"].lower():
        conv_mode = "llava_llama_2"
    elif "mistral" in model_info_dict["model_name"].lower():
        conv_mode = "mistral_instruct"
    elif "v1.6-34b" in model_info_dict["model_name"].lower():
        conv_mode = "chatml_direct"
    elif "v1" in model_info_dict["model_name"].lower():
        conv_mode = "llava_v1"
    elif "mpt" in model_info_dict["model_name"].lower():
        conv_mode = "mpt"
    else:
        conv_mode = "llava_v0"

    if run_config.conv_mode is not None and conv_mode != run_config.conv_mode:
        print(
            "[WARNING] the auto inferred conversation mode is {}, while `--conv-mode` is {}, using {}".format(
                conv_mode, run_config.conv_mode, run_config.conv_mode
            )
        )
    else:
        run_config.conv_mode = conv_mode

    conv = conv_templates[run_config.conv_mode].copy()
    conv.append_message(conv.roles[0], qs)
    conv.append_message(conv.roles[1], None)
    prompt = conv.get_prompt()

    input_ids = (
        tokenizer_image_token(prompt, model_info_dict["tokenizer"], IMAGE_TOKEN_INDEX, return_tensors="pt")
        .unsqueeze(0)
        .cuda()
    )

    model_info_dict["input_ids"] = input_ids

    return run_config, model_info_dict

def eval_model_image_process_only(run_config: LlavaRunConfig, model_info_dict):
    image_files = image_parser(run_config)
    images = load_images(image_files)
    image_sizes = [x.size for x in images]
    images_tensor = process_images(
        images,
        model_info_dict["image_processor"],
        model_info_dict["model"].config
    ).to(model_info_dict["model"].device, dtype=torch.float16)

    with torch.inference_mode():
        output_ids = model_info_dict["model"].generate(
            model_info_dict["input_ids"],
            images=images_tensor,
            image_sizes=image_sizes,
            do_sample=True if run_config.temperature > 0 else False,
            temperature=run_config.temperature,
            top_p=run_config.top_p,
            num_beams=run_config.num_beams,
            max_new_tokens=run_config.max_new_tokens,
            use_cache=True,
        )

    outputs = model_info_dict["tokenizer"].batch_decode(output_ids, skip_special_tokens=True)[0].strip()
    # empty cuda cache
    torch.cuda.empty_cache()
    return outputs


if __name__ == "__main__":
    parser = simple_parsing.ArgumentParser()
    parser.add_argument(LlavaRunConfig, dest="llava_run_config")
    args = parser.parse_args()

    eval_model(args.llava_run_config)
