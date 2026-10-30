## OPEN ACCESS

## Edited by:

Jialiang Yang,

Geneis (Beijing) Co. Ltd, China

## Reviewed by:

Shuhao Wang,

Tsinghua University, China

Zeyu Xing,

Chinese Academy of Medical

Sciences and Peking Union Medical

College, China

## \*Correspondence:

Feng Xu

[drxufeng@mail.ccmu.edu.cn](mailto:drxufeng@mail.ccmu.edu.cn)

Chuang Zhu

[czhu@bupt.edu.cn](mailto:czhu@bupt.edu.cn)

Mulan Jin

[kinmokuran@163.com](mailto:kinmokuran@163.com)

<sup>†</sup>These authors have contributed

equally to this work

## Specialty section:

This article was submitted to

Cancer Imaging and

Image-directed Interventions,

a section of the journal

Frontiers in Oncology

Received: 15 August 2021

Accepted: 21 September 2021

Published: 14 October 2021

## Citation:

Xu F, Zhu C, Tang W, Wang Y,

Zhang Y, Li J, Jiang H, Shi Z, Liu J and

Jin M (2021) Predicting Axillary Lymph

Node Metastasis in Early Breast

Cancer Using Deep Learning on

Primary Tumor Biopsy Slides.

Front. Oncol. 11:759007.

[doi: 10.3389/fonc.2021.759007](https://doi.org/10.3389/fonc.2021.759007)

# [Predicting Axillary Lymph Node Metastasis in Early Breast Cancer Using Deep Learning on Primary Tumor Biopsy Slides](https://www.frontiersin.org/articles/10.3389/fonc.2021.759007/full)

Feng Xu <sup>1\*†</sup>, Chuang Zhu<sup>2\*†</sup>, Wenqi Tang<sup>2†</sup>, Ying Wang <sup>3†</sup>, Yu Zhang<sup>2</sup>, Jie Li <sup>1</sup>, Hongchuan Jiang<sup>1</sup>, Zhongyue Shi <sup>3</sup>, Jun Liu<sup>2</sup> and Mulan Jin<sup>3\*</sup>

1 Department of Breast Surgery, Beijing Chao-Yang Hospital, Beijing, China, <sup>2</sup> School of Artificial Intelligence, Beijing University of Posts and Telecommunications, Beijing, China, <sup>3</sup> Department of Pathology, Beijing Chao-Yang Hospital, Beijing, China

Objectives: To develop and validate a deep learning (DL)-based primary tumor biopsy signature for predicting axillary lymph node (ALN) metastasis preoperatively in early breast cancer (EBC) patients with clinically negative ALN.

Methods: A total of 1,058 EBC patients with pathologically confirmed ALN status were enrolled from May 2010 to August 2020. A DL core-needle biopsy (DL-CNB) model was built on the attention-based multiple instance-learning (AMIL) framework to predict ALN status utilizing the DL features, which were extracted from the cancer areas of digitized whole-slide images (WSIs) of breast CNB specimens annotated by two pathologists. Accuracy, sensitivity, specificity, receiver operating characteristic (ROC) curves, and areas under the ROC curve (AUCs) were analyzed to evaluate our model.

Results: The best-performing DL-CNB model with VGG16\_BN as the feature extractor achieved an AUC of 0.816 (95% confidence interval (CI): 0.758, 0.865) in predicting positive ALN metastasis in the independent test cohort. Furthermore, our model incorporating the clinical data, which was called DL-CNB+C, yielded the best accuracy of 0.831 (95%CI: 0.775, 0.878), especially for patients younger than 50 years (AUC: 0.918, 95%CI: 0.825, 0.971). The interpretation of DL-CNB model showed that the top signatures most predictive of ALN metastasis were characterized by the nucleus features including density $\langle \rho   =   0 . 0 1 5 \rangle$ , circumference $\left( \rho   =   0.009 \right)$ , circularity $\langle p   =   0 . 0 1 0 \rangle$ , and orientation $\langle \rho = 0 . 0 1 2 \rangle$

Conclusion: Our study provides a novel DL-based biomarker on primary tumor CNB slides to predict the metastatic status of ALN preoperatively for patients with EBC.

Keywords: deep learning, axillary lymph node metastasis, breast cancer, core-needle biopsy, whole-slide images

## INTRODUCTION

Breast cancer (BC) has become the greatest threat to women’s health worldwide (1). Clinically, identification of axillary lymph node (ALN) metastasis is important for evaluating the prognosis and guiding the treatment for BC patients (2). Sentinel lymph node biopsy (SLNB) has gradually replaced ALN dissection (ALND) to identify ALN status, especially for early BC (EBC) patients with clinically negative lymph nodes. Although SLNB had the advantage of less invasiveness than ALND, SLNB still caused some complications such as lymphedema, axillary seroma, paraesthesia, and impaired shoulder function (3, 4). Moreover, SLNB has been considered a controversial procedure, owing to the availability of radionuclide tracers and the surgeon’s experience (5, 6). In fact, SLNB can be avoided if there are some reliable methods of preoperative prediction of ALN status for EBC patients.

Several studies intended to predict the ALN status by clinicopathological data and genetic testing score (7, 8). However, due to the relatively poor predictive values and high genetic testing costs, these methods are often limited. Recently, deep learning (DL) can perform high-throughput feature extraction on medical images and analyze the correlation between primary tumor features and ALN metastasis information. In a previous study, deep features extracted from conventional ultrasound and shear wave elastography (SWE) were used to predict ALN metastasis, presenting an area under the curve (AUC) of 0.796 in the test set (9). Nevertheless, SWE has not been integrated into routine clinical breast examinations in many hospitals. Another recent study demonstrated that the DL model based on diffusion-weighted imaging–magnetic resonance imaging (DWI-MRI) database of 172 patients achieved an AUC of 0.852 for preoperative prediction of ALN metastasis (10), but the small sample size enrolled could not be representative.

Currently, DL has enabled rapid advances in computational pathology (11, 12). For example, DL methods have been applied to segment and classify glomeruli with different staining and various pathologic changes, thus achieving the automatic analysis of renal biopsies (13, 14); meanwhile, DL-based automatic colonoscopy tissue segmentation and classification have shown promise for colorectal cancer detection (15, 16); besides, the analysis of gastric carcinoma and precancerous status can also benefit from DL schemes (17, 18). More recently, for the ALN metastasis detection, it is reported that DL algorithms on digital lymph node pathology images achieved better diagnostic efficiency of ALN metastasis than pathologists (19, 20). In particular, the assistance of algorithm significantly increases the sensitivity of detection for ALN micro-metastases (21). In addition to diagnosis, several previous studies indicated that deep features based on whole-slide images (WSIs) of postoperative tumor samples potentially improved the prediction performance of lymph node metastasis in a variety of cancers (20, 22). So far, there is no relevant research on preoperatively predicting ALN metastasis based on WSIs of primary BC samples. In this study, we investigated a clinical data set of EBC patients treated by preoperative core-needle biopsy (CNB) to determine whether DL models based on primary tumor biopsy slides could help to refine the prediction of ALN metastasis.

## PATIENTS AND METHODS

## Patients

On approval by the Institutional Ethical Committees of Beijing Chaoyang Hospital affiliated to Capital Medical University, we retrospectively analyzed data from EBC patients with clinically negative ALN from May 2010 to August 2020. Written consent was obtained from all patients and their families.

The detailed inclusion criteria were as follows: 1) patients with CNB pathologically confirmed primary invasive BC; 2) patients who underwent breast surgery with SLNB or ALND; 3) baseline clinicopathological data including age, tumor size, tumor type, ER/PR/HER-2 status, and the number of ALN metastasis were comprehensive; 4) complete concordance of molecular status was found between CNB and excision specimens; 5) no history of preoperative radiotherapy and chemotherapy; and 6) adequate volume of biopsy materials with three or more cores for each patient.

The exclusion criteria included the following: 1) patients with physically positive or imaging-positive ALN; 2) missing postoperative pathology information; 3) missing wax blocks and hematoxylin and eosin (H&E) slices; and 4) low-quality H&E slices or WSIs. The patient recruitment workflow is shown in Figure 1.

## Deep Learning Model Development

To avoid the inter-observer heterogeneity, all available tumor regions in each CNB slide were examined and annotated by two independent and experienced pathologists blinded to all patientrelated information. A WSI was classified into positive (N(+)) or negative (N0) using the proposed DL CNB (DL-CNB) model. Our DL-CNB model was constructed with the attention-based multiple-instance learning (MIL) approach (23). In MIL, each training sample was called a bag, which consisted of multiple instances (24–26) (each instance corresponds to an image patch of size 256 × 256 pixels). Different from the general fully supervised problem where each sample had a label, only the label of bags was available in MIL, and the goal of MIL was to predict the bag label by considering all included instances comprehensively. The whole algorithm pipeline comprised the following five steps:

(1) Training data preparation (Figure 2A). For each raw WSI, amounts of non-overlapping square patches were first cropped from the selected tumor regions. Then each WSI could be represented as a bag with N randomly selected patches. To increase the training samples, M bags were built for each WSI. All M bags were labeled as positive if the slide is an ALN metastasis case, and vice versa. Note that we could add the clinical information of the slide to all the M constructed bags to involve more useful information for predicting, and in this situation, the developed model was called DL-CNB+C.

![](images/page_2_image_2.jpg)

<details>
<summary>flowchart</summary>

```mermaid
graph TD
  A["Patients with CNB pathologically confirmed primary breast cancer from May 2010 to August 2020\nN=3020"] --> B["Patients with early invasive breast cancer\nN=1393"]
  A --> C["Excluded N=1627\nT3 or M1 stage N=561\nNo surgery after CNB N=403\nPathologically confirmed ductal carcinoma in situ N=225\nPhysically or imaging positive LNs N=438"]
  B --> D["Patients with standard CNB slides\nN=1058"]
  B --> E["Excluded N=335\nCNB specimens <3 for each patient N=183\nMissing wax blocks and HE slices N=25\nLow quality HE slices or WSI images N=83\nInconsistent ER/PR/HER-2 status between CNB and resected specimens N=44"]
  D --> F["LN metastasis\n403 individuals"]
  D --> G["No LN metastasis\n655 individuals"]
```
</details>

FIGURE 1 | Patient recruitment workflow.

(2) Feature extraction (left part of Figure 2B). N feature vectors were extracted for the N image instances in each bag by using a convolutional neural network (CNN) model. The performances of AlexNet (27), VGG16 (28) with batch norm (VGG16\_BN), ResNet50 (29), DenseNet121 (30), and Inceptionv3 (31) were compared to find the best feature extractor. At this stage, the clinical data were also preprocessed for feature extraction. Concretely, the numerical properties in clinical data were standardizing by removing the mean and scaling to unit variance, thus eliminating the effect of data range and scale; furthermore, considering that there was no natural ordinal relationship between different values of the category attributes, the categorical properties in clinical data were encoded as the one-hot vectors, which could express different values equally.
(3) MIL (right part of Figure 2B). The extracted Nfeature vectors of image instances were first processed by the max-pooling (32–34) and reshaping and then were passed to a two-layer fully connected (FC) layer. The Nweight factors for the instances in the bag were thus obtained and then were further multiplied to the original feature vectors (23) to adaptively adjust the effect of instance features. Finally, the weighted image feature vectors and the clinical features were fused by concatenation; due to the large difference of dimensions between image features and clinical features, the clinical features were copied 10 times for expansion. Then, the fused features were fed into the classifier, and the outputs and the ground truth labels were used to calculate the cross-entropy loss.
(4) Model training and testing. We randomly divided the WSIs into training cohort and independent test cohort with the ratio of 4:1 and randomly selected 25% of the training cohort as the validation cohort. We used Adam optimizer with learning rate 1e−4 to update the model parameters and weight decay 1e−3 for regularization. In the training phase, we used the cosine annealing warm restarts strategy to adjust the learning rate (35).

In the testing phase, the ALN status is predicted by aggregating the model outputs of all bags from the same slide (Figure 2C).

The DL models are available at: [https://github.com/bupt-ai-cz/BALNMP](https://github.com/bupt-ai-cz/BALNMP).

## Visualization of Salient Regions From Deep Learning Core-Needle Biopsy Model

We visualized the important regions that were more associated with metastatic status. After the processing of attention-based MIL pooling, the weights of different patches can be obtained, and the corresponding feature maps were then weighted together in the following FC layers to conduct ALN status prediction. With the attention weights, we created a heat map to visualize the important salient regions in each WSI.

## Interpretability of Deep Learning Core-Needle Biopsy Model With Nucleus Features

Interpretability of DL-CNB model with nucleus features was performed to study the contribution of different nucleus morphological characteristics in the prediction of lymph node metastasis (36, 37). Multiple specially designed nucleus features were firstly extracted for each WSI, and these features together formed a training bag. With the constructed feature bags, the proposed DL-CNB model was re-trained. The weights of different features (instances) can be obtained based on the attention-based MIL pooling, and thus the contribution of different features was yielded. The specific process is described in Figure 3.

## Statistical Analysis

The logistic regression was used to predict ALN status by clinical data only model. The clinical difference of N0 and N(+) was compared by using the Mann–Whitney U test and chi-square

![](images/page_3_image_2.jpg)

FIGURE 2 | The overall pipeline of the deep learning core-needle biopsy incorporating the clinical data (DL-CNB+C) model to predict axillary lymph node (ALN) status between N0 and N(+). (A) Multiple training bags were built based on clinical data and the cropped patches from the selected tumor regions of each core needle biopsy (CNB) whole-slide image (WSI). (B) DL-CNB+C model training process included two phases of feature extraction and multiple-instance learning (MIL), and finally the weighted features fused with clinical features were used to predict classification probabilities and calculate the cross-entropy loss. (C) The predicted probabilities of each bag from a raw CNB WSI were merged to guide the final ALN status classification between N0 and N(+).

![](images/page_3_image_4.jpg)

<details>
<summary>flowchart</summary>

```mermaid
graph LR
  A["WSI"] --> B["patch"]
  B --> C["nuclei segmentation"]
  C --> D["features"]
  D --> E["histogram"]
  E --> F["matrix"]
  F --> G["DL-CNB"]
  G --> H["output"]
  G --> I["feature weights"]
```
</details>

FIGURE 3 | Overview on interpretability methods of deep learning core-needle biopsy (DL-CNB) model based on nucleus morphometric features. (A) The selected tumor regions of each whole-slide image (WSI) was cropped into patches. (B) For each patch, we processed nucleus segmentation (a weakly supervised segmentation framework was applied to obtain the nucleus), defined multiple nucleus morphometric features (such as major axis, minor axis, area, orientation, circumference, density, circularity, and rectangularity, which are denoted as $f _ { 1 } , f _ { 2 } , f _ { 3 } ,   . . . , f _ { \eta } ) ,$ and extracted n feature parameters correspondingly. (C) All n kinds of feature parameters from a WSI were quantized into n distribution histograms and saved to n feature matrices $( m _ { 1 } , m _ { 2 } , m _ { 3 } ,   . . . ,   m _ { \triangle } ) .   ( { \pmb D } )$ The matrices from a WSI were considered as instances of a bag and served as the input of DL-CNB model; the re-trained DL-CNB model could generate scores of features (instances) in the bag, which represented the weight of each feature in pathological diagnosis.

test. The AUCs of different methods were compared by using Delong et al. (38). The other measurements like accuracy (ACC), sensitivity (SENS), specificity (SPEC), positive predictive value (PPV), and negative predictive value (NPV) were also used to estimate the model performance. All the statistics were twosided, and a p-value less than 0.05 was considered statistically significant. All statistical analyses were performed by MedCalc software (V 19.6.1; 2020 MedCalc Software bvba, Mariakerke, Belgium), Python 3.7, and SPSS 24.0 (IBM, Armonk, NY, USA).

## RESULTS

## Clinical Characteristics

A total of 1,058 patients with EBC were enrolled for analysis. Among them, 957 (90.5%) patients had invasive ductal carcinomas, and 101 (9.5%) patients had invasive lobular carcinomas. There were 840 patients in the training cohort and 218 patients in the independent test cohort after all WSIs were randomly divided by using N0 as the negative reference standard and others as the positive. The average patient age was 57.6 years (range, 26–90 years) for the training and validation sets and 56.7 years (range, 22–87 years) for the test set. The mean ultrasound tumor size was 2.23 cm (range, 0.5–4.5 cm). A total of 556 patients (52.6%) had T1 tumors, while 502 patients (47.4%) had T2 tumors. According to the results of SLNB or ALND, positive lymph nodes were found in 403 patients. Among them, 210 patients (52.1%) had one or two positive lymph nodes (N+(1 − 2)), and 193 patients (47.9%) had three or more positive lymph nodes $\left(  N _{+}(\geq 3) \right)$ . As shown in Table 1, there was no significant difference between the detailed characteristics of the training and independent test cohorts (all $p > 0 . 0 5 )$

## Convolutional Neural Network Model Selection

The detailed results are summarized in Supplementary Table 1. Based on the overall analysis, VGG16\_BN model pre-trained on ImageNet (39) provided the best performance in the validation cohort and the independent test cohort (AUC: 0.808, 0.816), compared with AlexNet (AUC: 0.764, 0.780), ResNet50 (AUC: 0.644, 0.607), DenseNet121 (AUC: 0.714, 0.739), and Inception-v3 (AUC: 0.753, 0.762). Furthermore, considering other metrics, VGG16\_BN achieved the best ACC, SPEC, and PPV in the independent test cohort. VGG16\_BN consisted of (convolution layer, batch normalization layer, and Rectified Linear Unit (ReLU)) as the basic block where ReLU played a role of activation function to provide the non-linear capability; and max-pooling layers were inserted between basic blocks for down-sampling; besides, there was an adaptive average pooling layer at the end of VGG16\_BN for obtaining features with a fixed size. The details of VGG16\_BN are described in Supplementary Table 2.

## Predictive Value of Deep Learning Core-Needle Biopsy Incorporating the Clinical Data Model Between N0 and N(+)

In the training cohort, DL-CNB+C achieved an AUC of 0.878, while DL-CNB and classification by clinical data only model achieved AUCs of 0.901 and 0.661, respectively. And in the validation cohort, the DL-CNB+C model achieved an AUC of 0.823, which was higher than an AUC of 0.808 obtained by DL-CNB only and an AUC of 0.709 obtained by classification by clinical data.

In the independent test cohort, the DL-CNB+C model still achieved the highest AUC of 0.831, which was better than the AUC of DL-CNB only (AUC: 0.816, p = 0.453) and classification by clinical data only (AUC: 0.613, $p < 0 . 0 0 0 1 )$ . The ACC, SENS, and NPV of DL-CNB+C were also better than those of other methods. The detailed statistical results are summarized in Table 2, and its corresponding receiver operating characteristics (ROCs) are shown in Figure 4.

TABLE 1 | Patient and tumor characteristics.

| Characteristics |  | All patients | Training | Test | p |
| --- | --- | --- | --- | --- | --- |
| Number |  | 1,058 | 840 (80%) | 218 (20%) |  |
| Age, mean ± SD, years |  | 57.58 ± 12.523 | 57.80 ± 12.481 | 56.72 ± 12.674 | 0.344 |
| Tumor size, mean ± SD, cm |  | 2.234 ± 0.8623 | 2.228 ± 0.8516 | 2.256 ± 0.9040 | 0.898 |
| Number of LNM, mean ± SD |  | 1.20 ± 2.081 | 1.20 ± 2.095 | 1.20 ± 2.033 | 0.847 |
| Tumor type |  |  |  |  | 0.812 |
|  | Invasive ductal carcinoma | 957 | 760 (90.5%) | 197 (90.4%) |  |
|  | Invasive lobular carcinoma | 101 | 80 (9.5%) | 21 (9.6%) |  |
| T stage |  |  |  |  | 0.327 |
|  | T1 | 556 | 435 (51.8%) | 121 (55.5%) |  |
|  | T2 | 502 | 405 (48.2%) | 97 (44.5%) |  |
| ER |  |  |  |  | 0.333 |
|  | Positive | 831 | 665 (79.2%) | 166 (76.1%) |  |
|  | Negative | 227 | 175 (20.8%) | 52 (23.9%) |  |
| PR |  |  |  |  | 0.312 |
|  | Positive | 790 | 633 (75.4%) | 157 (72.0%) |  |
|  | Negative | 268 | 207 (24.6%) | 61 (28.0%) |  |
| HER-2 |  |  |  |  | 0.613 |
|  | Positive | 277 | 217 (25.8%) | 60 (27.5%) |  |
|  | Negative | 781 | 623 (74.2%) | 158 (72.5%) |  |
| LNM |  |  |  |  | 0.880 |
|  | Yes | 403 | 521 (62.0%) | 134 (61.5%) |  |
|  | No | 655 | 319 (38.0%) | 84 (38.5%) |  |

Qualitative variables are in n (%), and quantitative variables are in mean ± SD, when appropriate. SD, standard deviation; ER, estrogen receptor; PR, progesterone receptor; HER-2, human epidermal growth factor receptor-2; LNM, lymph node metastasis.

We further divided N(+) into low metastatic potential (N+ (1 − 2)) and high metastatic potential (N+(≥3)) according to the number of ALN metastasis. Adopting N0 as the negative reference standard, the combined model showed better discriminating ability between N0 and $\mathrm { N _ { + } } ( 1   -   2 )$ (AUC: 0.878) and between N0 and N+(≥3) (AUC: 0.838).

The detailed statistical results are summarized in Supplementary Tables 3, 4, and the corresponding ROCs are shown in Supplementary Figures 1, 2.

## Predictive Value of Deep Learning Core-Needle Biopsy Incorporating the Clinical Data Model Among N0, $\mathsf { N } _ { + } ( \bar { 1 } - 2 )$ and N+(≥3)

The overall AUC of multi-classification in the independent test cohort based on DL-CNB+C model was 0.791; there existed the highest precision and recall of 0.747 and 0.947, respectively, in N0; there existed the precision and recall of 0.556 and 0.400 in $\mathrm { N } _ { + }$ (1 − 2); and there existed the precision and recall of 0.375 and 0.162 in $\mathrm { N _ { + } ( \geq } 3 \mathrm { ) }$ . The confusion matrix under the classification threshold of 0.5 is shown in Figure 5. According to the results, the model performed well in differentiating the N0 group while showing poor diagnostic efficacy in the other two groups.

TABLE 2 | The performance in prediction of ALN status (N0 vs. N(+)).

<table><tr><td>Methods</td><td></td><td>AUC</td><td>ACC (%)</td><td>SENS (%)</td><td>SPEC (%)</td><td>PPV (%)</td><td>NPV (%)</td></tr><tr><td rowspan="3">Clinical data only</td><td>T</td><td>0.661 [0.622, 0.698]</td><td>64.13 [60.24, 67.88]</td><td>64.58 [58.17, 70.63]</td><td>63.85 [58.86, 68.62]</td><td>52.36 [48.32, 56.38]</td><td>74.55 [70.85, 77.92]</td></tr><tr><td>V</td><td>0.709 [0.643, 0.770]</td><td>67.62 [60.84, 73.90]</td><td>65.82 [54.29, 76.13]</td><td>68.70 [60.02, 76.52]</td><td>55.91 [48.46, 63.11]</td><td>76.92 [70.62, 82.22]</td></tr><tr><td>I-T</td><td> $0.613^{a,b}$  [0.545, 0.678]</td><td>61.93 [55.12, 68.40]</td><td>50.00 [38.89, 61.11]</td><td>69.40 [60.86, 77.07]</td><td>50.60 [42.34, 58.83]</td><td>68.89 [63.49, 73.82]</td></tr><tr><td rowspan="3">DL-CNB model</td><td>T</td><td>0.901 [0.875, 0.923]</td><td>80.32 [76.99, 83.35]</td><td>94.17 [90.41, 96.77]</td><td>71.79 [67.05, 76.21]</td><td>67.26 [63.61, 70.71]</td><td>95.24 [92.30, 97.09]</td></tr><tr><td>V</td><td>0.808 [0.748, 0.859]</td><td>72.86 [66.31, 78.75]</td><td>77.22 [66.40, 85.90]</td><td>70.23 [61.62, 77.90]</td><td>61.00 [53.95, 67.62]</td><td>83.64 [77.04, 88.62]</td></tr><tr><td>I-T</td><td> $0.816^c$  [0.758, 0.865]</td><td>74.77 [68.46, 80.39]</td><td>80.95 [70.92, 88.70]</td><td>70.90 [62.43, 78.42]</td><td>63.55 [56.76, 69.84]</td><td>85.59 [79.04, 90.34]</td></tr><tr><td rowspan="3">DL-CNB+C model</td><td>T</td><td>0.878 [0.622, 0.698]</td><td>76.51 [73.00, 79.77]</td><td>93.33 [89.40, 96.14]</td><td>66.15 [61.22, 70.84]</td><td>62.92 [59.53, 66.19]</td><td>94.16 [90.90, 96.30]</td></tr><tr><td>V</td><td>0.823 [0.765, 0.872]</td><td>75.71 [69.34, 81.35]</td><td>74.68 [63.64, 83.80]</td><td>76.34 [68.12, 83.32]</td><td>65.56 [57.69, 72.65]</td><td>83.33 [77.19, 88.08]</td></tr><tr><td>I-T</td><td>0.831 [0.775, 0.878]</td><td>75.69 [69.44, 81.23]</td><td>89.29 [80.63, 94.98]</td><td>67.16 [58.53, 75.03]</td><td>63.03 [56.96, 68.71]</td><td>90.91 [84.21, 94.94]</td></tr></table>

95% confidence intervals are included in brackets.

AUC, area under the receiver operating characteristic curve; ACC, accuracy; SENS, sensitivity; SPEC, specificity; PPV, positive predictive value; NPV, negative predictive value; $T ,$ training cohort (n = 630); V, validation cohort $( n = 2 7 0 ) ; 1 - T ,$ independent test cohort $( n = 2 7 8 ) ; A L N ,$ axillary lymph node; DL-CNB+C, deep learning core-needle biopsy incorporating the clinical data.

<sup>a</sup>Indicates p < 0.0001, Delong et al. in comparison with $D L - C N B$ model in independent test cohort.

<sup>b</sup>Indicates $p < 0 . 0 0 0 1 ,$ Delong et al. in comparison with $DL - CNB + C$ model in independent test cohort.

<sup>c</sup>Indicates $p = 0 . 4 5 3 2 ,$ Delong et al. in comparison with DL-CNB+C model in independent test cohort.

![](images/page_5_chart_15.jpg)

<details>
<summary>roc</summary>

| 1-Specificity | Clinical data only (Sensitivity) | DL-CNB (Sensitivity) | DL-CNB+C (Sensitivity) |
| --- | --- | --- | --- |
| 0.0 | 0.0 | 0.0 | 0.0 |
| ~0.05 | ~0.1 | ~0.25 | ~0.25 |
| ~0.1 | ~0.2 | ~0.4 | ~0.4 |
| ~0.2 | ~0.3 | ~0.6 | ~0.7 |
| ~0.3 | ~0.45 | ~0.75 | ~0.8 |
| ~0.4 | ~0.55 | ~0.85 | ~0.9 |
| ~0.5 | ~0.65 | ~0.95 | ~0.95 |
| ~0.6 | ~0.75 | ~1.0 | ~1.0 |
| ~0.7 | ~0.85 | 1.0 | 1.0 |
| ~0.8 | ~0.9 | 1.0 | 1.0 |
| ~0.9 | ~0.95 | 1.0 | 1.0 |
| 1.0 | 1.0 | 1.0 | 1.0 |
</details>

FIGURE 4 | Comparison of receiver operating characteristic (ROC) curves between different models for predicting disease-free axilla (N0) and heavy metastatic burden of axillary disease (N(+)). Numbers in parentheses are areas under the receiver operating characteristic curve (AUCs).

![](images/page_6_chart_2.jpg)

<details>
<summary>confusion</summary>

| Ground Truth | Predicted Label::N0 | Predicted Label::N+(1-2) | Predicted Label::\(N+(\ge 3)\) |
| --- | --- | --- | --- |
| N0 | 124 | 2 | 5 |
| N+(1-2) | 25 | 20 | 5 |
| \(N+(\ge 3)\) | 17 | 14 | 6 |
</details>

FIGURE 5 | The confusion matrix of predicting axillary lymph node (ALN) status between disease-free axilla (N0), low metastatic burden of axillary disease (N+(1 − 2)), and heavy metastatic burden of axillary disease (N+(≥3)).

## Subgroup Analysis of Deep Learning Core-Needle Biopsy Incorporating the Clinical Data Model

Furthermore, we analyzed the measurement results of the different subgroups in the independent test cohort of predicting ALN status between N0 and N(+) by the DL-$\scriptstyle \mathrm { C N B + C }$ model. The detailed statistical results are summarized in Supplementary Table 5. In the independent test cohort, compared with an AUC of 0.794 (95%CI: 0.720, 0.855) in the subgroup of age >50, there existed better performance in the subgroup of age ≤50 with an AUC of 0.918 (95%CI: 0.825, 0.971, $p = 0 . 0 1 5 )$ . There were no significant differences regarding other subgroups of ER(+) vs. ER(−) (p = 0.125), PR(+) vs. PR(−) (p = 0.659), HER-2(+) vs. HER-2(−) (p = 0.524), and T1 vs. T2 stage $( p = 0 . 7 4 3 )$ between N0 and N(+).

## Interpretability of Deep Learning Core-Needle Biopsy Model

To investigate the interpretability of the DL-CNB, we conducted two studies for digging the correlation factors of ALN status prediction. In the first study, we adopted the attention-based MIL pooling to find the important regions that contributing to the prediction. The heat map in Figure 6A highlights the red patches as the important regions. Although the obtained important areas can provide some clues to the diagnosis of DL-CNB model, it is not clear that the model makes decisions based on what features of the tumor area.

In the second study, we specially designed and extracted multiple nucleus features for each WSI. The weights of different features were then obtained based on the same attention-based MIL pooling in our DL-CNB. The weights highlighted the nucleus features that were most relevant to the ALN status prediction of each WSI. We found that the WSI of N(+) group had higher nuclear density $\left( p = 0 . 0 1 5 \right)$ and orientation $\left( p = 0 . 0 1 2 \right)$ but lower circumference $( p = 0 . 0 0 9 )$ , circularity $( p   =   0 . 0 1 0 )$ , and area $( p =$ 0.024) compared with N0 group (Figures 6B, C). There were no significant differences in other nucleus features including major axis $( p   =   0 . 0 8 3 )$ , minor axis $( p   =   0 . 0 6 5 )$ , and rectangularity $( p =$ 0.149) between N0 and N(+).

## DISCUSSION

In most previous studies, DL signatures of ALN metastases were based on medical images such as ultrasound, CT, and MRI (10, 40, 41). However, since many patients had undergone CNB at the time of imaging examination, and the reactive changes such as needle path in the tumor would result in the predictive inaccuracy of imaging information. This study focused on preoperative CNB WSI, which also played an important role in BC management and has been increasingly performed in clinical practice. Preoperative CNB can provide not only the histopathological diagnosis of BC but also the molecular status including ER/PR/HER-2 status, which is associated with ALN metastasis (42). Otherwise, the morphological features of tumor cells can be visualized on CNB WSI. Therefore, primary tumor biopsy WSI as a complementary imaging tool has the potential for ALN metastasis prediction. To the best of our knowledge, this is the first study to apply the DL-based histopathological features extracted from primary tumor WSIs for ALN prediction analysis.

Here, the best-performing DL-CNB model yielded satisfactory predictions with an AUC of 0.816, a SENS of 81.0%, and a SPEC of 70.9% on the test set, which had superior predictive capability as compared with clinical data alone. Furthermore, unlike other combined models incorporating clinical data (7, 9), the DL-CNB+C model slightly improved the ACC to 0.831, which showed that our results were mainly derived from the contribution of DL-CNB model. In addition, during the subgroup analysis stratified by patient’s age, our DL-CNB+C model achieved an AUC of 0.918 for patients younger than 50 years, indicating that age was the critical factor in predicting ALN status. Regarding the number of ALN metastasis, the DL-CNB+C model showed better discriminating ability between N0 and N+(1 − 2), and between N0 and N+(≥3). However, the unfavorable discriminating ability was found between $\mathrm { N } _ { + } ( 1 \mathrm { ~ - ~ } 2 )$ and N+(≥3). This was consistent with the study of Zheng et al. (9), who also reported poor efficacy between $\mathrm { N } _ { + } ( 1   -   2 )$ and N+(≥3), utilizing the DL radiomics model. In the future, further exploration of ALN staging prediction is needed.

A

![](images/page_7_image_3.jpg)

C

FIGURE 6 | The interpretability of the deep learning core-needle biopsy (DL-CNB) model of two patients. (A, B) The heat maps and nuclear segmentation from core-needle biopsy (CNB) whole-slide images (WSIs) of the N0 and the N(+) separately, and the red regions show greater contribution to the final classification. (C) The statistical analysis of three nuclear characteristics most relevant to diagnosis of all patients.

Indeed, computer-assisted histopathological analysis can provide a more practical and objective output (43). For example, different molecular subtypes (44) and Oncotype DX risk score (45) occurring in BC could be directly predicted from the H&E slides. On the one hand, our DL model can provide significant information for risk stratification and axillary staging, thereby avoiding axillary surgery and reducing the complication and hospitalization costs. On the other hand, our results also highlight the development of algorithms based on artificial intelligence, which will reduce the labor intensity of pathologists. Similar approaches may be used to the pathology of other organs.

In our study, we are first to quantitatively assess the role of nuclear disorder in predicting ALN metastasis in BC. Our finding is consistent with several recent studies that demonstrate the powerful predictive effect of nuclear disorder on patient survival (46, 47). Interestingly, the top predictive signatures that distinguished N0 from N(+) were characterized by the nucleus features including density, circumference, circularity, and orientation. We found that the WSI of N(+) had higher nuclear density and polarity but lower circularity, which was understandable since in the tumors with ALN metastasis, tumor cells became poorly differentiated as a result of rapid cell growth, encouraging the nuclei in these structures to form highly clustered and consistently metastatic patterns. Our results showed that nuanced patterns of nucleus density and orientation of tumor cells are important determinants of ALN metastasis.

There are some limitations in our study. First, the selection of regions of interest within each CNB slide required pathologist guidance. Future studies will explore more advanced methods for automatic segmentation of tumor regions. Second, this is a retrospective study, and prospective validation of our model in a large multicenter cohort of EBC patients is necessary to assess the clinical applicability of the biomarker. Third, recent evidence indicated that a set of features related to tumor-infiltrating lymphocytes (TILs) was found to be associated with positive LNs in bladder cancer (22). However, due to few TILs on breast CNB slides, we only selected sufficient tumor cells for the identification of salient regions rather than whole slides. Finally, we only chose H&E stained images of CNB samples. The clinical utility of immunochemical stained images remains to be established as an interesting attempt.

## CONCLUSION

In brief, we demonstrated that a novel DL-based biomarker on primary tumor CNB slides predicted ALN metastasis preoperatively for EBC patients with clinically negative ALN, especially for younger patients. Our methods could help to avoid unnecessary axillary surgery based on the widely collected H&Estained histopathology slides, thereby contributing to precision oncology treatment.

## REFERENCES

1. Siegel RL, Miller KD, Jemal A. Cancer Statistics, 2019. CA Cancer J Clin (2019) 69(1):7–34. doi: [10.3322/caac.21551](https://doi.org/10.3322/caac.21551)
2. Ahmed M, Purushotham AD, Douek M. Novel Techniques for Sentinel Lymph Node Biopsy in Breast Cancer: A Systematic Review. Lancet Oncol (2014) 15(8):e351–62. doi: [10.1016/S1470-2045(13)70590-4](https://doi.org/10.1016/S1470-2045%2813%2970590-4)
3. Kootstra J, Hoekstra-Weebers JEHM, Rietman H, de Vries J, Baas P, Geertzen JHB, et al. Quality of Life After Sentinel Lymph Node Biopsy or Axillary Lymph Node Dissection in Stage I/II Breast Cancer Patients: A Prospective Longitudinal Study. Ann Surg Oncol (2008) 15(9):2533–41. doi: [10.1245/ s10434-008-9996-9](https://doi.org/10.1245/s10434-008-9996-9)
4. Wilke LG, McCall LM, Posther KE, Whitworth PW, Reintgen DS, Leitch AM, et al. Surgical Complications Associated With Sentinel Lymph Node Biopsy: Results From a Prospective International Cooperative Group Trial. Ann Surg Oncol (2006) 13(4):491–500. doi: [10.1245/ASO.2006.05.013](https://doi.org/10.1245/ASO.2006.05.013)
5. Manca G, Rubello D, Tardelli E, Giammarile F, Mazzarri S, Boni G, et al. Sentinel Lymph Node Biopsy in Breast Cancer: Indications, Contraindications, and Controversies. Clin Nucl Med (2016) 41(2):126–33. doi: [10.1097/RLU.0000000000000985](https://doi.org/10.1097/RLU.0000000000000985)
6. Hindié E, Groheux D, Brenot-Rossi I, Rubello D, Moretti J-L, Espié M. The Sentinel Node Procedure in Breast Cancer: Nuclear Medicine as the Starting Point. J Nucl Med (2011) 52(3):405–14. doi: [10.2967/jnumed.110.081711](https://doi.org/10.2967/jnumed.110.081711)

## DATA AVAILABILITY STATEMENT

The original contributions presented in the study are included in the article/Supplementary Material. Further inquiries can be directed to the corresponding authors.

## ETHICS STATEMENT

Written informed consent was obtained from the individual(s) for the publication of any potentially identifiable images or data included in this article.

## AUTHOR CONTRIBUTIONS

FX, CZ, JiL, YW, and MJ designed the study. CZ, WT, YZ, and JiL trained the model. FX, YW, ZS, JuL, and HJ collected the data. FX, WT, YZ, CZ, YW, MJ, and JuL analyzed and interpreted the data. FX, CZ, WT, YZ, and MJ prepared the manuscript. All authors contributed to the article and approved the submitted version.

## FUNDING

The work was supported by National Natural Science Foundation of China [No. 8197101438].

## SUPPLEMENTARY MATERIAL

The Supplementary Material for this article can be found online at: [https://www.frontiersin.org/articles/10.3389/fonc.2021.759007/full#supplementary-material](https://www.frontiersin.org/articles/10.3389/fonc.2021.759007/full#supplementary-material)

7. Dihge L, Vallon-Christersson J, Hegardt C, Saal LH, Häkkinen J, Larsson C, et al. Prediction of Lymph Node Metastasis in Breast Cancer by Gene Expression and Clinicopathological Models: Development and Validation Within a Population-Based Cohort. Clin Cancer Res (2019) 25(21):6368–81. doi: [10.1158/1078-0432.CCR-19-0075](https://doi.org/10.1158/1078-0432.CCR-19-0075)
8. Shiino S, Matsuzaki J, Shimomura A, Kawauchi J, Takizawa S, Sakamoto H, et al. Serum Mirna–Based Prediction of Axillary Lymph Node Metastasis in Breast Cancer. Clin Cancer Res (2019) 25(6):1817–27. doi: [10.1158/1078-0432.CCR-18-1414](https://doi.org/10.1158/1078-0432.CCR-18-1414)
9. Zheng X, Yao Z, Huang Y, Yu Y, Wang Y, Liu Y, et al. Deep Learning Radiomics Can Predict Axillary Lymph Node Status in Early-Stage Breast Cancer. Nat Commun (2020) 11(1):1236. doi: [10.1038/s41467-020-15027-z](https://doi.org/10.1038/s41467-020-15027-z)
10. Luo J, Ning Z, Zhang S, Feng Q, Zhang Y. Bag of Deep Features for Preoperative Prediction of Sentinel Lymph Node Metastasis in Breast Cancer. Phys Med Biol (2018) 63(24):245014. doi: [10.1088/1361-6560/aaf241](https://doi.org/10.1088/1361-6560/aaf241)
11. Campanella G, Hanna MG, Geneslaw L, Miraflor A, Werneck Krauss Silva V, Busam KJ, et al. Clinical-Grade Computational Pathology Using Weakly Supervised Deep Learning on Whole Slide Images. Nat Med (2019) 25 (8):1301–9. doi: [10.1038/s41591-019-0508-1](https://doi.org/10.1038/s41591-019-0508-1)
12. Gu F, Burlutskiy N, Andersson M, Wilén LK. Multi-Resolution Networks for Semantic Segmentation in Whole Slide Images. In: Computational Pathology and Ophthalmic Medical Image Analysis; 2018. Cham, Switzerland: Springer International Publishing (2018). p. 11–8. doi: [10.1007/978-3-030-00949-6\_2](https://doi.org/10.1007/978-3-030-00949-6_2)
13. Mei K, Zhu C, Jiang L, Liu J, Qiao Y. Cross-Stained Segmentation From Renal Biopsy Images Using Multi-Level Adversarial Learning. In: IEEE International Conference on Acoustics, Speech and Signal Processing; 2020. IEEE (2020). p. 1424–8. doi: [10.1109/ICASSP40776.2020.9054505](https://doi.org/10.1109/ICASSP40776.2020.9054505)
14. Jiang L, Chen W, Dong B, Mei K, Zhu C, Liu J, et al. A Deep Learning-Based Approach for Glomeruli Instance Segmentation From Multistained Renal Biopsy Pathologic Images. Am J Pathol (2021) 191(8):1431–41. doi: [10.1016/ j.ajpath.2021.05.004](https://doi.org/10.1016/j.ajpath.2021.05.004)
15. Zhu C, Mei K, Peng T, Luo Y, Liu J, Wang Y, et al. Multi-Level Colonoscopy Malignant Tissue Detection With Adversarial CAC-Unet. Neurocomputing (2021) 438:165–83. doi: [10.1016/j.neucom.2020.04.154](https://doi.org/10.1016/j.neucom.2020.04.154)
16. Feng R, Liu X, Chen J, Chen DZ, Gao H, Wu J. A Deep Learning Approach for Colonoscopy Pathology WSI Analysis: Accurate Segmentation and Classification. IEEE J BioMed Health Inform (2020). doi: [10.1109/ JBHI.2020.3040269](https://doi.org/10.1109/JBHI.2020.3040269)
17. Iizuka O, Kanavati F, Kato K, Rambeau M, Arihiro K, Tsuneki M. Deep Learning Models for Histopathological Classification of Gastric and Colonic Epithelial Tumours. Sci Rep (2020) 10(1):1504. doi: [10.1038/s41598-020-58467-9](https://doi.org/10.1038/s41598-020-58467-9)
18. Song Z, Zou S, Zhou W, Huang Y, Shao L, Yuan J, et al. Clinically Applicable Histopathological Diagnosis System for Gastric Cancer Detection Using Deep Learning. Nat Commun (2020) 11(1):4294. doi: [10.1038/s41467-020-18147-8](https://doi.org/10.1038/s41467-020-18147-8)
19. Hu Y, Su F, Dong K, Wang X, Zhao X, Jiang Y, et al. Deep Learning System for Lymph Node Quantification and Metastatic Cancer Identification From Whole-Slide Pathology Images. Gastric Cancer (2021) 24(4):868–77. doi: [10.1007/s10120-021-01158-9](https://doi.org/10.1007/s10120-021-01158-9)
20. Zhao Y, Yang F, Fang Y, Liu H, Zhou N, Zhang J, et al. Predicting Lymph Node Metastasis Using Histopathological Images Based on Multiple Instance Learning With Deep Graph Convolution. In: Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition; 2020. IEEE (2020). p. 4837–46. doi: [10.1109/CVPR42600.2020.00489](https://doi.org/10.1109/CVPR42600.2020.00489)
21. Steiner DF, MacDonald R, Liu Y, Truszkowski P, Hipp JD, Gammage C, et al. Impact of Deep Learning Assistance on the Histopathologic Review of Lymph Nodes for Metastatic Breast Cancer. Am J Surg Pathol (2018) 42(12):1636–46. doi: [10.1097/PAS.0000000000001151](https://doi.org/10.1097/PAS.0000000000001151)
22. Harmon SA, Sanford TH, Brown GT, Yang C, Mehralivand S, Jacob JM, et al. Multiresolution Application of Artificial Intelligence in Digital Pathology for Prediction of Positive Lymph Nodes From Primary Tumors in Bladder Cancer. JCO Clin Cancer Inform (2020) 4:367–82. doi: [10.1200/CCI.19.00155](https://doi.org/10.1200/CCI.19.00155)
23. Ilse M, Tomczak J, Welling M. Attention-Based Deep Multiple Instance Learning. In: Proceedings of the International Conference on Machine Learning PMLR (2018). p. 2127–36.
24. Das K, Conjeti S, Roy AG, Chatterjee J, Sheet D. Multiple Instance Learning of Deep Convolutional Neural Networks for Breast Histopathology Whole Slide Classification. In: IEEE International Symposium on Biomedical Imaging; 2018. IEEE (2018). p. 578–81. doi: [10.1109/ISBI.2018.8363642](https://doi.org/10.1109/ISBI.2018.8363642)
25. Sudharshan PJ, Petitjean C, Spanhol F, Oliveira LE, Heutte L, Honeine P. Multiple Instance Learning for Histopathological Breast Cancer Image Classification. Expert Syst Appl (2019) 117:103–11. doi: [10.1016/j.eswa.2018.09.049](https://doi.org/10.1016/j.eswa.2018.09.049)
26. Couture HD, Marron JS, Perou CM, Troester MA, Niethammer M. Multiple Instance Learning for Heterogeneous Images: Training a CNN for Histopathology. In: Medical Image Computing and Computer Assisted Intervention; 2018. Cham, Switzerland: Springer International Publishing (2018). p. 254–62. doi: [10.1007/978-3-030-00934-2\_29](https://doi.org/10.1007/978-3-030-00934-2_29)
27. Krizhevsky A, Sutskever I, Hinton GE. Imagenet Classification With Deep Convolutional Neural Networks. Commun ACM (2017) 60(6):84–90. doi: [10.1145/3065386](https://doi.org/10.1145/3065386)
28. Simonyan K, Zisserman A. Very Deep Convolutional Networks for Large-Scale Image Recognition. In: International Conference on Learning Representations; 2015. ICLR (2015).
29. He K, Zhang X, Ren S, Sun J. Deep Residual Learning for Image Recognition. In: Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition; 2016. IEEE (2016). p. 770–8. doi: [10.1109/CVPR.2016.90](https://doi.org/10.1109/CVPR.2016.90)
30. Huang G, Liu Z, van der Maaten L, Weinberger KQ. Densely Connected Convolutional Networks. In: Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition; 2017. IEEE (2017). p. 4700–8. doi: [10.1109/ CVPR.2017.243](https://doi.org/10.1109/CVPR.2017.243)
31. Szegedy C, Vanhoucke V, Ioffe S, Shlens J, Wojna Z. Rethinking the Inception Architecture for Computer Vision. In: Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition; 2016. IEEE (2016). p. 2818–26. doi: [10.1109/CVPR.2016.308](https://doi.org/10.1109/CVPR.2016.308)
32. Feng J, Zhou Z-H. Deep Miml Network. In: Proceedings of the AAAI Conference on Artificial Intelligence; 2017. AAAI Press (2017). p. 1884–90.
33. Pinheiro PO, Collobert R. From Image-Level to Pixel-Level Labeling With Convolutional Networks. In: Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition; 2015 IEEE (2015). p. 1713–21. doi: [10.1109/ CVPR.2015.7298780](https://doi.org/10.1109/CVPR.2015.7298780)
34. Zhu W, Lou Q, Vang YS, Xie X. Deep Multi-Instance Networks With Sparse Label Assignment for Whole Mammogram Classification Medical Image Computing and Computer Assisted Intervention; 2017. Cham, Switzerland: Springer International Publishing (2017) p. 603–11. doi: [10.1007/978-3-319-66179-7\_69](https://doi.org/10.1007/978-3-319-66179-7_69)
35. Loshchilov I, Hutter F. SGDR: Stochastic Gradient Descent With Warm Restarts. In: International Conference on Learning Representations; 2017. ICLR (2017).
36. Mueller JL, Gallagher JE, Chitalia R, Krieger M, Erkanli A, Willett RM, et al. Rapid Staining and Imaging of Subnuclear Features to Differentiate Between Malignant and Benign Breast Tissues at a Point-of-Care Setting. J Cancer Res Clin Oncol (2016) 142(7):1475–86. doi: [10.1007/s00432-016-2165-9](https://doi.org/10.1007/s00432-016-2165-9)
37. Radhakrishnan A, Damodaran K, Soylemezoglu AC, Uhler C, Shivashankar GV. Machine Learning for Nuclear Mechano-Morphometric Biomarkers in Cancer Diagnosis. Sci Rep (2017) 7(1):17946. doi: [10.1038/s41598-017-17858-1](https://doi.org/10.1038/s41598-017-17858-1)
38. DeLong ER, DeLong DM, Clarke-Pearson DL. Comparing the Areas Under Two or More Correlated Receiver Operating Characteristic Curves: A Nonparametric Approach. Biometrics (1988) 44(3):837–45. doi: [10.1038/ s41591-019-0508-1](https://doi.org/10.1038/s41591-019-0508-1)
39. Deng J, Dong W, Socher R, Li L-J, Li K, Fei-Fei L. Imagenet: A Large-Scale Hierarchical Image Database. In: Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition; 2009. IEEE (2009). p. 248–55.
40. Zhou L-Q, Wu X-L, Huang S-Y, Wu G-G, Ye H-R, Wei Q, et al. Lymph Node Metastasis Prediction From Primary Breast Cancer US Images Using Deep Learning. Radiology (2020) 294(1):19–28. doi: [10.1148/radiol.2019190372](https://doi.org/10.1148/radiol.2019190372)
41. Yang X, Wu L, Ye W, Zhao K, Wang Y, Liu W, et al. Deep Learning Signature Based on Staging CT for Preoperative Prediction of Sentinel Lymph Node Metastasis in Breast Cancer. Acad Radiol (2020) 27(9):1226–33. doi: [10.1016/ j.acra.2019.11.007](https://doi.org/10.1016/j.acra.2019.11.007)
42. Calhoun KE, Anderson BO. Needle Biopsy for Breast Cancer Diagnosis: A Quality Metric for Breast Surgical Practice. J Clin Oncol (2014) 32(21):2191–2. doi: [10.1200/JCO.2014.55.6324](https://doi.org/10.1200/JCO.2014.55.6324)
43. Acs B, Rantalainen M, Hartman J. Artificial Intelligence as the Next Step Towards Precision Pathology. J Intern Med (2020) 288(1):62–81. doi: [10.1111/joim.13030](https://doi.org/10.1111/joim.13030)
44. Jaber MI, Song B, Taylor C, Vaske CJ, Benz SC, Rabizadeh S, et al. A Deep Learning Image-Based Intrinsic Molecular Subtype Classifier of Breast Tumors Reveals Tumor Heterogeneity That may Affect Survival. Breast Cancer Res (2020) 22(1):12. doi: [10.1186/s13058-020-1248-3](https://doi.org/10.1186/s13058-020-1248-3)
45. Whitney J, Corredor G, Janowczyk A, Ganesan S, Doyle S, Tomaszewski J, et al. Quantitative Nuclear Histomorphometry Predicts Oncotype DX Risk Categories for Early Stage ER+ Breast Cancer. BMC Cancer (2018) 18(1):610. doi: [10.1186/s12885-018-4448-9](https://doi.org/10.1186/s12885-018-4448-9)
46. Lu C, Romo-Bucheli D, Wang X, Janowczyk A, Ganesan S, Gilmore H, et al. Nuclear Shape and Orientation Features From H&E Images Predict Survival in Early-Stage Estrogen Receptor-Positive Breast Cancers. Lab Invest (2018) 98(11):1438–48. doi: [10.1038/s41374-018-0095-7](https://doi.org/10.1038/s41374-018-0095-7)
47. Lee G, Veltri RW, Zhu G, Ali S, Epstein JI, Madabhushi A. Nuclear Shape and Architecture in Benign Fields Predict Biochemical Recurrence in Prostate Cancer Patients Following Radical Prostatectomy: Preliminary Findings. Eur Urol Focus (2017) 3(4):457–66. doi: [10.1016/j.euf.2016.05.009](https://doi.org/10.1016/j.euf.2016.05.009)

Conflict of Interest: The authors declare that the research was conducted in the absence of any commercial or financial relationships that could be construed as a potential conflict of interest.

Publisher’s Note: All claims expressed in this article are solely those of the authors and do not necessarily represent those of their affiliated organizations, or those of the publisher, the editors and the reviewers. Any product that may be evaluated in this article, or claim that may be made by its manufacturer, is not guaranteed or endorsed by the publisher.

Copyright © 2021 Xu, Zhu, Tang, Wang, Zhang, Li, Jiang, Shi, Liu and Jin. This is an open-access article distributed under the terms of the [Creative Commons Attribution](http://creativecommons.org/licenses/by/4.0/)

[License (CC BY)](http://creativecommons.org/licenses/by/4.0/). The use, distribution or reproduction in other forums is permitted, provided the original author(s) and the copyright owner(s) are credited and that the original publication in this journal is cited, in accordance with accepted academic practice. No use, distribution or reproduction is permitted which does not comply with these terms.